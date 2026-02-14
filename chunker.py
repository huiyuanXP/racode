"""
File chunking logic for code search indexer.

Splits files into semantically coherent chunks based on file type:
- Markdown: Split at headings (##, ###)
- Python: Split at top-level functions and classes
- TypeScript: Split at export declarations
- Other: Single full-file chunk
"""

import re
from typing import List, Dict, Any
from pathlib import Path


class Chunk:
    """Represents a single chunk of file content."""
    
    def __init__(
        self,
        file_path: str,
        chunk_type: str,
        symbol_name: str,
        content: str,
        line_start: int,
        line_end: int,
        is_doc_file: bool = False
    ):
        self.file_path = file_path
        self.chunk_type = chunk_type
        self.symbol_name = symbol_name
        self.content = content
        self.line_start = line_start
        self.line_end = line_end
        self.is_doc_file = is_doc_file
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary for database insertion."""
        return {
            "file_path": self.file_path,
            "chunk_type": self.chunk_type,
            "symbol_name": self.symbol_name,
            "content": self.content,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "is_doc_file": 1 if self.is_doc_file else 0
        }


def chunk_markdown(file_path: str, content: str) -> List[Chunk]:
    """
    Chunk Markdown files by headings (## and ###).
    
    Content before first heading becomes 'module_header'.
    Each heading section becomes a separate chunk.
    
    Args:
        file_path: Path to the file
        content: File content as string
        
    Returns:
        List of Chunk objects
    """
    lines = content.split('\n')
    chunks = []
    current_chunk_lines = []
    current_heading = None
    current_start_line = 1
    is_doc_file = file_path.endswith(('FileStructure.md', 'IntegrationGuide.md'))
    
    for i, line in enumerate(lines, start=1):
        # Check for heading (## or ###)
        heading_match = re.match(r'^(#{2,3})\s+(.+)$', line)
        
        if heading_match:
            # Save previous chunk if exists
            if current_chunk_lines:
                chunk_content = '\n'.join(current_chunk_lines).strip()
                if chunk_content:
                    chunks.append(Chunk(
                        file_path=file_path,
                        chunk_type='module_header' if current_heading is None else 'section',
                        symbol_name=current_heading or '',
                        content=chunk_content,
                        line_start=current_start_line,
                        line_end=i - 1,
                        is_doc_file=is_doc_file
                    ))
            
            # Start new chunk
            current_heading = heading_match.group(2).strip()
            current_chunk_lines = [line]
            current_start_line = i
        else:
            current_chunk_lines.append(line)
    
    # Save final chunk
    if current_chunk_lines:
        chunk_content = '\n'.join(current_chunk_lines).strip()
        if chunk_content:
            chunks.append(Chunk(
                file_path=file_path,
                chunk_type='module_header' if current_heading is None else 'section',
                symbol_name=current_heading or '',
                content=chunk_content,
                line_start=current_start_line,
                line_end=len(lines),
                is_doc_file=is_doc_file
            ))
    
    return chunks


def chunk_python(file_path: str, content: str) -> List[Chunk]:
    """
    Chunk Python files by top-level functions and classes.
    
    Splits at 'def' and 'class' at column 0, including decorators.
    Module imports and constants become 'module_header'.
    
    Args:
        file_path: Path to the file
        content: File content as string
        
    Returns:
        List of Chunk objects
    """
    lines = content.split('\n')
    chunks = []
    current_chunk_lines = []
    current_symbol = None
    current_type = 'module_header'
    current_start_line = 1
    decorator_lines = []
    
    for i, line in enumerate(lines, start=1):
        # Check for decorator at column 0
        if re.match(r'^@\w+', line):
            decorator_lines.append(line)
            continue
        
        # Check for top-level def or class at column 0
        func_match = re.match(r'^(def|class)\s+(\w+)', line)
        
        if func_match:
            # Save previous chunk if exists
            if current_chunk_lines:
                chunk_content = '\n'.join(current_chunk_lines).strip()
                if chunk_content:
                    chunks.append(Chunk(
                        file_path=file_path,
                        chunk_type=current_type,
                        symbol_name=current_symbol or '',
                        content=chunk_content,
                        line_start=current_start_line,
                        line_end=i - 1 - len(decorator_lines),
                        is_doc_file=False
                    ))
            
            # Start new chunk with decorators
            current_symbol = func_match.group(2)
            current_type = 'function' if func_match.group(1) == 'def' else 'class'
            current_chunk_lines = decorator_lines + [line]
            current_start_line = i - len(decorator_lines)
            decorator_lines = []
        else:
            # Regular line
            if decorator_lines:
                # Decorator without def/class following - add to current chunk
                current_chunk_lines.extend(decorator_lines)
                decorator_lines = []
            current_chunk_lines.append(line)
    
    # Save final chunk
    if current_chunk_lines:
        chunk_content = '\n'.join(current_chunk_lines).strip()
        if chunk_content:
            chunks.append(Chunk(
                file_path=file_path,
                chunk_type=current_type,
                symbol_name=current_symbol or '',
                content=chunk_content,
                line_start=current_start_line,
                line_end=len(lines),
                is_doc_file=False
            ))
    
    return chunks


def chunk_typescript(file_path: str, content: str) -> List[Chunk]:
    """
    Chunk TypeScript/TSX files by export declarations.
    
    Splits at:
    - export function
    - export class
    - export interface
    - export const (arrow functions)
    - Non-exported top-level equivalents
    
    Args:
        file_path: Path to the file
        content: File content as string
        
    Returns:
        List of Chunk objects
    """
    lines = content.split('\n')
    chunks = []
    current_chunk_lines = []
    current_symbol = None
    current_type = 'module_header'
    current_start_line = 1
    
    for i, line in enumerate(lines, start=1):
        # Check for export or top-level declarations
        export_match = re.match(
            r'^(?:export\s+)?(?:(function|class|interface|const|type|enum))\s+(\w+)',
            line
        )
        
        if export_match:
            # Save previous chunk if exists
            if current_chunk_lines:
                chunk_content = '\n'.join(current_chunk_lines).strip()
                if chunk_content:
                    chunks.append(Chunk(
                        file_path=file_path,
                        chunk_type=current_type,
                        symbol_name=current_symbol or '',
                        content=chunk_content,
                        line_start=current_start_line,
                        line_end=i - 1,
                        is_doc_file=False
                    ))
            
            # Start new chunk
            current_symbol = export_match.group(2)
            current_type = export_match.group(1)
            current_chunk_lines = [line]
            current_start_line = i
        else:
            current_chunk_lines.append(line)
    
    # Save final chunk
    if current_chunk_lines:
        chunk_content = '\n'.join(current_chunk_lines).strip()
        if chunk_content:
            chunks.append(Chunk(
                file_path=file_path,
                chunk_type=current_type,
                symbol_name=current_symbol or '',
                content=chunk_content,
                line_start=current_start_line,
                line_end=len(lines),
                is_doc_file=False
            ))
    
    return chunks


def chunk_file(file_path: str) -> List[Chunk]:
    """
    Chunk a file based on its extension.
    
    Args:
        file_path: Path to the file to chunk
        
    Returns:
        List of Chunk objects
        
    Raises:
        FileNotFoundError: If file does not exist
        UnicodeDecodeError: If file cannot be decoded as UTF-8
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        content = path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(
            e.encoding, e.object, e.start, e.end,
            f"Cannot decode file {file_path} as UTF-8"
        )
    
    # Determine chunking strategy based on file extension
    suffix = path.suffix.lower()
    
    if suffix == '.md':
        return chunk_markdown(file_path, content)
    elif suffix == '.py':
        return chunk_python(file_path, content)
    elif suffix in {'.ts', '.tsx', '.js', '.jsx'}:
        return chunk_typescript(file_path, content)
    else:
        # Single full-file chunk for other types
        return [Chunk(
            file_path=file_path,
            chunk_type='full_file',
            symbol_name='',
            content=content,
            line_start=1,
            line_end=len(content.split('\n')),
            is_doc_file=False
        )]
