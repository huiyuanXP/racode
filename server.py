#!/usr/bin/env python3
"""
RACode (Retrieval-Augmented Code Search)

Provides intelligent code search using SQLite FTS5 with BM25 ranking and LSP integration.
Unlike traditional RAG (embeddings), RACode uses precise keyword matching + compiler-grade
symbol resolution — all running locally with zero external API calls.

Tools:
- code_search_search: Full-text search with BM25 ranking
- code_search_get_references: Find symbol references (LSP)
- code_search_get_definition: Find symbol definitions (LSP)
- code_search_rebuild_index: Force full index rebuild
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum

import re

from mcp.server.fastmcp import FastMCP
from indexer import CodeSearchIndexer
from lsp_bridge import LSPBridge


CONTEXT_LINES = 10  # Total lines to show around keyword match


def _trim_content_around_keyword(content: str, query: str, context_lines: int = CONTEXT_LINES) -> str:
    """
    Extract a window of lines around the first keyword match within a chunk.

    The keyword line is placed roughly at line 5 of the window (0-indexed: 4),
    with equal context above and below. If the match is near the top of the
    chunk, the window shifts downward (and vice-versa) so we always return
    up to *context_lines* lines without exceeding chunk boundaries.
    """
    lines = content.split('\n')

    # Chunk already fits within the window -- return as-is
    if len(lines) <= context_lines:
        return content

    # Build a case-insensitive pattern from each query token
    tokens = query.strip().split()
    pattern = re.compile('|'.join(re.escape(t) for t in tokens), re.IGNORECASE)

    # Find the first matching line
    match_idx = 0
    for i, line in enumerate(lines):
        if pattern.search(line):
            match_idx = i
            break

    # Calculate window: place match at position 4 (5th line) within the window
    above = context_lines // 2          # 5
    below = context_lines - above - 1   # 4

    start = match_idx - above
    end = match_idx + below + 1  # exclusive

    # Shift window when hitting chunk boundaries
    if start < 0:
        end = min(len(lines), end + (-start))
        start = 0
    if end > len(lines):
        start = max(0, start - (end - len(lines)))
        end = len(lines)

    return '\n'.join(lines[start:end])


# Initialize MCP server
mcp = FastMCP("racode")

# Global indexer and LSP bridge instances
indexer: Optional[CodeSearchIndexer] = None
lsp_bridge: Optional[LSPBridge] = None


class ExtensionFilter(str, Enum):
    """File extension filter options."""
    ALL = "*"
    MARKDOWN = ".md"
    PYTHON = ".py"
    TYPESCRIPT = ".ts,.tsx"
    JAVASCRIPT = ".js,.jsx"
    CONFIG = ".json,.yaml,.yml,.toml"


class SearchInput(BaseModel):
    """Input model for code_search_search tool."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    query: str = Field(
        ...,
        description="Search query string. Use simple keywords, avoid special characters. Examples: 'authentication', 'model selector', 'get_gpt_service'",
        min_length=1,
        max_length=200
    )
    
    extensions: str = Field(
        default=".md",
        description="Comma-separated file extensions to search (e.g., '.py,.ts' or '*' for all files). Common options: '.md' (documentation), '.py' (Python), '.ts,.tsx' (TypeScript), '*' (all files)",
        max_length=100
    )
    
    limit: int = Field(
        default=5,
        description="Maximum number of results to return",
        ge=1,
        le=50
    )
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate search query."""
        if not v.strip():
            raise ValueError("Search query cannot be empty")
        return v.strip()
    
    @field_validator('extensions')
    @classmethod
    def validate_extensions(cls, v: str) -> str:
        """Validate extensions format."""
        v = v.strip()
        if not v:
            return "*"
        return v


class LanguageOption(str, Enum):
    """Supported programming languages for LSP."""
    PYTHON = "python"
    TYPESCRIPT = "typescript"


class SymbolLookupInput(BaseModel):
    """Input model for LSP symbol lookup tools."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    symbol: str = Field(
        ...,
        description="Symbol name to look up. Examples: 'get_gpt_service', 'ModelSelector', 'useAuth'",
        min_length=1,
        max_length=200
    )
    
    language: LanguageOption = Field(
        default=LanguageOption.PYTHON,
        description="Programming language of the symbol. Options: 'python' or 'typescript'"
    )
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol name."""
        if not v.strip():
            raise ValueError("Symbol name cannot be empty")
        return v.strip()


@mcp.tool(
    name="code_search_search",
    annotations={
        "title": "Search Code with BM25 Ranking",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def search(params: SearchInput) -> str:
    """
    Search the codebase using full-text search with BM25 ranking.
    
    This tool performs intelligent code search across the project, automatically
    prioritizing documentation files (FileStructure.md, IntegrationGuide.md) with
    3x ranking boost. The index is automatically updated before each search to
    ensure results reflect the latest code changes.
    
    Use this tool when you need to:
    - Find code related to a specific feature or concept
    - Locate documentation about a system component
    - Discover where certain functionality is implemented
    - Search for specific keywords across the codebase
    
    Args:
        params (SearchInput): Search parameters containing:
            - query (str): Search keywords (e.g., "authentication", "model selector")
            - extensions (str): File types to search (default: ".md" for docs)
            - limit (int): Max results to return (default: 10, max: 50)
    
    Returns:
        str: JSON array of search results, each containing:
            - file_path: Relative path to the file
            - chunk_type: Type of code chunk (function, class, section, etc.)
            - symbol_name: Name of the symbol (function/class name or heading)
            - content: The actual code or documentation content
            - line_start: Starting line number
            - line_end: Ending line number
            - score: Relevance score (higher is better)
    
    Examples:
        - Search docs for "authentication": query="authentication", extensions=".md"
        - Search Python code: query="get_gpt_service", extensions=".py"
        - Search all files: query="model selector", extensions="*"
    
    Error handling:
        - Invalid query syntax: Returns error message with guidance
        - No results found: Returns empty array with suggestion to broaden search
    """
    if not indexer:
        return json.dumps({
            "error": "Indexer not initialized. Please provide --project-root argument."
        }, indent=2)
    
    try:
        # Perform incremental update before search
        indexer.incremental_update()
        
        # Parse extensions
        if params.extensions == "*":
            ext_list = None
        else:
            ext_list = [ext.strip() for ext in params.extensions.split(',')]
        
        # Perform search
        results = indexer.search(
            query=params.query,
            extensions=ext_list,
            limit=params.limit
        )
        
        if not results:
            return json.dumps({
                "results": [],
                "message": f"No results found for query '{params.query}'. Try using different keywords or search all files with extensions='*'."
            }, indent=2)

        # Trim markdown results to ~10 lines around the keyword match;
        # code files keep their full chunk content for structural context
        for result in results:
            if result['file_path'].endswith('.md'):
                result['content'] = _trim_content_around_keyword(
                    result['content'], params.query
                )

        return json.dumps({
            "results": results,
            "count": len(results),
            "query": params.query
        }, indent=2)
        
    except ValueError as e:
        return json.dumps({
            "error": f"Search query error: {str(e)}. Please use simple keywords and avoid special characters."
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Search failed: {str(e)}"
        }, indent=2)


@mcp.tool(
    name="code_search_get_references",
    annotations={
        "title": "Find Symbol References (LSP)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_references(params: SymbolLookupInput) -> str:
    """
    Find all references to a symbol in the codebase using LSP.
    
    This tool uses Language Server Protocol integration to find where a symbol
    (function, class, variable, etc.) is referenced throughout the codebase.
    
    - Python: Uses jedi for accurate in-process symbol resolution
    - TypeScript: Uses ts-morph via Node.js subprocess for full compiler API access
    
    Use this tool when you need to:
    - Find all usages of a function or class
    - Understand where a component is being used
    - Track dependencies and call sites
    - Refactor code safely by knowing all references
    
    Args:
        params (SymbolLookupInput): Lookup parameters containing:
            - symbol (str): Symbol name to find references for
            - language (str): Programming language ("python" or "typescript")
    
    Returns:
        str: JSON array of reference locations, each containing:
            - file_path: Relative path to the file
            - line: Line number of the reference
            - column: Column number of the reference
            - context: Surrounding code context
            - kind: Type of reference (function_call, import, etc.)
    
    Examples:
        - Find Python function usage: symbol="get_gpt_service", language="python"
        - Find TypeScript component usage: symbol="ModelSelector", language="typescript"
    
    Error handling:
        - Symbol not found: Returns empty array with suggestion to check spelling
        - Language not supported: Returns error with supported languages list
    """
    if not lsp_bridge:
        return json.dumps({
            "error": "LSP bridge not initialized. Please provide --project-root argument."
        }, indent=2)
    
    try:
        if params.language == LanguageOption.PYTHON:
            results = lsp_bridge.get_python_references(params.symbol)
        elif params.language == LanguageOption.TYPESCRIPT:
            results = lsp_bridge.get_typescript_references(params.symbol)
        else:
            return json.dumps({
                "error": f"Unsupported language: {params.language}. Supported: python, typescript"
            }, indent=2)
        
        if not results:
            return json.dumps({
                "results": [],
                "message": f"No references found for symbol '{params.symbol}'. Check spelling or try searching with code_search_search."
            }, indent=2)
        
        return json.dumps({
            "results": results,
            "count": len(results),
            "symbol": params.symbol,
            "language": params.language
        }, indent=2)
        
    except RuntimeError as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Failed to find references: {str(e)}"
        }, indent=2)


@mcp.tool(
    name="code_search_get_definition",
    annotations={
        "title": "Find Symbol Definition (LSP)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def get_definition(params: SymbolLookupInput) -> str:
    """
    Find the definition location of a symbol using LSP.
    
    This tool uses Language Server Protocol integration to locate where a symbol
    (function, class, variable, etc.) is defined in the codebase.
    
    - Python: Uses jedi for accurate in-process symbol resolution
    - TypeScript: Uses ts-morph via Node.js subprocess for full compiler API access
    
    Use this tool when you need to:
    - Jump to the definition of a function or class
    - Understand how a component is implemented
    - Navigate to the source of an imported symbol
    - Explore code structure and organization
    
    Args:
        params (SymbolLookupInput): Lookup parameters containing:
            - symbol (str): Symbol name to find definition for
            - language (str): Programming language ("python" or "typescript")
    
    Returns:
        str: JSON array of definition locations (usually one), each containing:
            - file_path: Relative path to the file
            - line: Line number of the definition
            - column: Column number of the definition
            - context: The definition code
            - kind: Type of definition (function_definition, class_definition, etc.)
    
    Examples:
        - Find Python function: symbol="get_gpt_service", language="python"
        - Find TypeScript component: symbol="ModelSelector", language="typescript"
    
    Error handling:
        - Symbol not found: Returns empty array with suggestion to use search tool
        - Language not supported: Returns error with supported languages list
    """
    if not lsp_bridge:
        return json.dumps({
            "error": "LSP bridge not initialized. Please provide --project-root argument."
        }, indent=2)
    
    try:
        if params.language == LanguageOption.PYTHON:
            results = lsp_bridge.get_python_definition(params.symbol)
        elif params.language == LanguageOption.TYPESCRIPT:
            results = lsp_bridge.get_typescript_definition(params.symbol)
        else:
            return json.dumps({
                "error": f"Unsupported language: {params.language}. Supported: python, typescript"
            }, indent=2)
        
        if not results:
            return json.dumps({
                "results": [],
                "message": f"No definition found for symbol '{params.symbol}'. Check spelling or try searching with code_search_search."
            }, indent=2)
        
        return json.dumps({
            "results": results,
            "count": len(results),
            "symbol": params.symbol,
            "language": params.language
        }, indent=2)
        
    except RuntimeError as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Failed to find definition: {str(e)}"
        }, indent=2)


@mcp.tool(
    name="code_search_rebuild_index",
    annotations={
        "title": "Rebuild Search Index",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False
    }
)
async def rebuild_index() -> str:
    """
    Force a complete rebuild of the search index.
    
    This tool clears the existing index and re-indexes all files from scratch.
    Normally not needed as the index is automatically updated incrementally
    before each search. Use this only if you suspect index corruption or want
    to ensure a completely fresh index.
    
    Use this tool when:
    - You suspect the index is corrupted or out of sync
    - You want to force a complete re-index after major code changes
    - Troubleshooting search issues
    
    Note: This operation may take several seconds for large codebases.
    
    Returns:
        str: JSON object with rebuild statistics:
            - files_indexed: Number of files processed
            - chunks_created: Number of code chunks created
            - duration_seconds: Time taken to rebuild
            - errors: List of any errors encountered
    
    Error handling:
        - File access errors: Logged in errors array, indexing continues
        - Parse errors: Logged in errors array, file skipped
    """
    if not indexer:
        return json.dumps({
            "error": "Indexer not initialized. Please provide --project-root argument."
        }, indent=2)
    
    try:
        stats = indexer.rebuild_index()
        return json.dumps({
            "success": True,
            "statistics": stats
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "error": f"Index rebuild failed: {str(e)}"
        }, indent=2)


def main():
    """Main entry point for the MCP server."""
    global indexer, lsp_bridge
    
    parser = argparse.ArgumentParser(description="Code Search MCP Server")
    parser.add_argument(
        "--project-root",
        type=str,
        required=True,
        help="Root directory of the project to index"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to SQLite database file (default: <project-root>/.code_search.db)"
    )
    
    args = parser.parse_args()
    
    # Validate project root
    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)
    
    # Set database path
    db_path = args.db_path or str(project_root / ".code_search.db")
    
    # Initialize indexer
    print(f"Initializing code search indexer...", file=sys.stderr)
    print(f"Project root: {project_root}", file=sys.stderr)
    print(f"Database: {db_path}", file=sys.stderr)
    
    indexer = CodeSearchIndexer(db_path=db_path, project_root=str(project_root))
    
    # Initialize LSP bridge
    print(f"Initializing LSP bridge...", file=sys.stderr)
    lsp_bridge = LSPBridge(project_root=str(project_root))
    
    # Perform initial incremental update
    print(f"Performing initial index update...", file=sys.stderr)
    stats = indexer.incremental_update()
    print(f"Index ready: {stats['files_new'] + stats['files_modified'] + stats['files_unchanged']} files, "
          f"{stats['chunks_created']} chunks created in {stats['duration_seconds']}s", file=sys.stderr)
    
    # Run MCP server
    print(f"Starting MCP server...", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
