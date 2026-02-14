"""
FTS5 indexing engine for code search.

Provides:
- SQLite FTS5 database with BM25 ranking
- Incremental indexing based on mtime comparison
- Search with document boost (3x for FileStructure.md/IntegrationGuide.md)
- Full index rebuild capability
"""

import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from chunker import chunk_file, Chunk


# Directories to skip during indexing
SKIP_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv',
    'dist', 'build', '.next', '.cache', 'coverage'
}

# File extensions to index
INDEXABLE_EXTENSIONS = {
    '.py', '.ts', '.tsx', '.js', '.jsx', '.md',
    '.txt', '.json', '.yaml', '.yml', '.toml'
}


class CodeSearchIndexer:
    """FTS5-based code search indexer with incremental updates."""
    
    def __init__(self, db_path: str, project_root: str):
        """
        Initialize the indexer.
        
        Args:
            db_path: Path to SQLite database file
            project_root: Root directory of the project to index
        """
        self.db_path = db_path
        self.project_root = Path(project_root).resolve()
        self.conn: Optional[sqlite3.Connection] = None
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize database schema if not exists."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # File metadata table for incremental updates
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS file_meta (
                file_path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # Backing content table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks_content (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                symbol_name TEXT NOT NULL,
                content TEXT NOT NULL,
                line_start INTEGER NOT NULL,
                line_end INTEGER NOT NULL,
                is_doc_file INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # FTS5 virtual table (external content mode)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                file_path, chunk_type, symbol_name, content,
                line_start UNINDEXED, line_end UNINDEXED, is_doc_file UNINDEXED,
                content='chunks_content', content_rowid='rowid'
            )
        """)
        
        # Sync triggers for FTS5
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks_content BEGIN
                INSERT INTO chunks(rowid, file_path, chunk_type, symbol_name, content)
                VALUES (new.rowid, new.file_path, new.chunk_type, new.symbol_name, new.content);
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks_content BEGIN
                DELETE FROM chunks WHERE rowid = old.rowid;
            END
        """)
        
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks_content BEGIN
                UPDATE chunks SET 
                    file_path = new.file_path,
                    chunk_type = new.chunk_type,
                    symbol_name = new.symbol_name,
                    content = new.content
                WHERE rowid = new.rowid;
            END
        """)
        
        self.conn.commit()
    
    def _collect_files(self) -> Dict[str, int]:
        """
        Walk project tree and collect file paths with mtime.
        
        Returns:
            Dictionary mapping file path to mtime_ns
        """
        files = {}
        
        for path in self.project_root.rglob('*'):
            # Skip directories
            if path.is_dir():
                continue
            
            # Skip if in excluded directory
            if any(skip_dir in path.parts for skip_dir in SKIP_DIRS):
                continue
            
            # Skip if not indexable extension
            if path.suffix.lower() not in INDEXABLE_EXTENSIONS:
                continue
            
            # Get relative path from project root
            try:
                rel_path = str(path.relative_to(self.project_root))
                mtime_ns = path.stat().st_mtime_ns
                files[rel_path] = mtime_ns
            except (OSError, ValueError):
                # Skip files we can't access
                continue
        
        return files
    
    def _classify_files(
        self, current_files: Dict[str, int]
    ) -> Dict[str, Set[str]]:
        """
        Classify files as new, modified, deleted, or unchanged.
        
        Args:
            current_files: Dictionary of current file paths to mtime_ns
            
        Returns:
            Dictionary with keys: 'new', 'modified', 'deleted', 'unchanged'
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT file_path, mtime_ns FROM file_meta")
        stored_files = {row['file_path']: row['mtime_ns'] for row in cursor.fetchall()}
        
        classification = {
            'new': set(),
            'modified': set(),
            'deleted': set(),
            'unchanged': set()
        }
        
        # Check current files
        for file_path, mtime_ns in current_files.items():
            if file_path not in stored_files:
                classification['new'].add(file_path)
            elif stored_files[file_path] != mtime_ns:
                classification['modified'].add(file_path)
            else:
                classification['unchanged'].add(file_path)
        
        # Check for deleted files
        for file_path in stored_files:
            if file_path not in current_files:
                classification['deleted'].add(file_path)
        
        return classification
    
    def _remove_file_chunks(self, file_path: str) -> None:
        """
        Remove all chunks for a file.
        
        Args:
            file_path: Relative path to the file
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chunks_content WHERE file_path = ?", (file_path,))
        cursor.execute("DELETE FROM file_meta WHERE file_path = ?", (file_path,))
    
    def _index_file(self, file_path: str, mtime_ns: int) -> int:
        """
        Index a single file.
        
        Args:
            file_path: Relative path to the file
            mtime_ns: File modification time in nanoseconds
            
        Returns:
            Number of chunks created
        """
        full_path = self.project_root / file_path
        
        try:
            chunks = chunk_file(str(full_path))
        except (FileNotFoundError, UnicodeDecodeError) as e:
            # Skip files that can't be read
            return 0
        
        cursor = self.conn.cursor()
        
        # Insert chunks
        for chunk in chunks:
            chunk_dict = chunk.to_dict()
            cursor.execute("""
                INSERT INTO chunks_content (
                    file_path, chunk_type, symbol_name, content,
                    line_start, line_end, is_doc_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_dict['file_path'],
                chunk_dict['chunk_type'],
                chunk_dict['symbol_name'],
                chunk_dict['content'],
                chunk_dict['line_start'],
                chunk_dict['line_end'],
                chunk_dict['is_doc_file']
            ))
        
        # Update file metadata
        cursor.execute("""
            INSERT OR REPLACE INTO file_meta (file_path, mtime_ns, chunk_count)
            VALUES (?, ?, ?)
        """, (file_path, mtime_ns, len(chunks)))
        
        return len(chunks)
    
    def incremental_update(self) -> Dict[str, Any]:
        """
        Perform incremental index update.
        
        Only re-indexes files that have been added, modified, or deleted
        since the last update.
        
        Returns:
            Statistics dictionary with keys:
            - files_new, files_modified, files_deleted, files_unchanged
            - chunks_created, chunks_removed
            - duration_seconds
        """
        start_time = time.time()
        
        # Collect current files
        current_files = self._collect_files()
        
        # Classify files
        classification = self._classify_files(current_files)
        
        chunks_created = 0
        chunks_removed = 0
        errors = []
        
        # Process in a single transaction
        try:
            # Remove deleted files
            for file_path in classification['deleted']:
                self._remove_file_chunks(file_path)
                chunks_removed += 1
            
            # Re-index modified files
            for file_path in classification['modified']:
                self._remove_file_chunks(file_path)
                chunks_removed += 1
                try:
                    chunks_created += self._index_file(file_path, current_files[file_path])
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")
            
            # Index new files
            for file_path in classification['new']:
                try:
                    chunks_created += self._index_file(file_path, current_files[file_path])
                except Exception as e:
                    errors.append(f"{file_path}: {str(e)}")
            
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise RuntimeError(f"Incremental update failed: {str(e)}")
        
        duration = time.time() - start_time
        
        return {
            'files_new': len(classification['new']),
            'files_modified': len(classification['modified']),
            'files_deleted': len(classification['deleted']),
            'files_unchanged': len(classification['unchanged']),
            'chunks_created': chunks_created,
            'chunks_removed': chunks_removed,
            'duration_seconds': round(duration, 3),
            'errors': errors
        }
    
    def rebuild_index(self) -> Dict[str, Any]:
        """
        Force full rebuild of the index.
        
        Clears all existing data and re-indexes all files.
        
        Returns:
            Statistics dictionary with keys:
            - files_indexed, chunks_created, duration_seconds, errors
        """
        start_time = time.time()
        
        # Clear existing data
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chunks_content")
        cursor.execute("DELETE FROM file_meta")
        self.conn.commit()
        
        # Collect and index all files
        current_files = self._collect_files()
        chunks_created = 0
        errors = []
        
        for file_path, mtime_ns in current_files.items():
            try:
                chunks_created += self._index_file(file_path, mtime_ns)
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")
        
        self.conn.commit()
        
        duration = time.time() - start_time
        
        return {
            'files_indexed': len(current_files),
            'chunks_created': chunks_created,
            'duration_seconds': round(duration, 3),
            'errors': errors
        }
    
    def search(
        self,
        query: str,
        extensions: Optional[List[str]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search the index with BM25 ranking and document boost.
        
        Args:
            query: Search query string
            extensions: List of file extensions to filter (e.g., ['.py', '.md'])
                       If None or ['*'], search all files
            limit: Maximum number of results to return
            
        Returns:
            List of result dictionaries with keys:
            - file_path, chunk_type, symbol_name, content
            - line_start, line_end, score
        """
        cursor = self.conn.cursor()
        
        # Build extension filter
        extension_filter = ""
        if extensions and '*' not in extensions:
            # Create OR conditions for each extension
            ext_conditions = " OR ".join([
                f"c.file_path LIKE '%{ext}'" for ext in extensions
            ])
            extension_filter = f" AND ({ext_conditions})"
        
        # Search with document boost (3x for FileStructure.md/IntegrationGuide.md)
        query_sql = f"""
            SELECT 
                c.file_path,
                c.chunk_type,
                c.symbol_name,
                c.content,
                c.line_start,
                c.line_end,
                rank * CASE WHEN c.is_doc_file = 1 THEN 3.0 ELSE 1.0 END AS score
            FROM chunks
            JOIN chunks_content c ON chunks.rowid = c.rowid
            WHERE chunks MATCH ?{extension_filter}
            ORDER BY score
            LIMIT ?
        """
        
        try:
            cursor.execute(query_sql, (query, limit))
            results = []
            
            for row in cursor.fetchall():
                results.append({
                    'file_path': row['file_path'],
                    'chunk_type': row['chunk_type'],
                    'symbol_name': row['symbol_name'],
                    'content': row['content'],
                    'line_start': row['line_start'],
                    'line_end': row['line_end'],
                    'score': round(row['score'], 2)
                })
            
            return results
        except sqlite3.OperationalError as e:
            # Handle FTS5 query syntax errors
            raise ValueError(f"Invalid search query: {str(e)}")
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
