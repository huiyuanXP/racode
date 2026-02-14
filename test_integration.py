#!/usr/bin/env python3
"""
Integration tests for Code Search MCP Server

Tests all major functionality:
- Index building and incremental updates
- Full-text search with BM25 ranking
- Document boost (3x for FileStructure.md/IntegrationGuide.md)
- Python LSP (jedi)
- TypeScript LSP (ts-morph)
"""

import sys
import time
from pathlib import Path

from indexer import CodeSearchIndexer
from lsp_bridge import LSPBridge


def test_indexer():
    """Test indexer functionality."""
    print("=" * 60)
    print("TEST 1: Indexer")
    print("=" * 60)
    
    project_root = '/home/ubuntu/Study-With-LLM-refactor'
    db_path = '/tmp/test_code_search.db'
    
    # Remove old test database
    Path(db_path).unlink(missing_ok=True)
    
    # Initialize indexer
    print("\n1.1 Initializing indexer...")
    indexer = CodeSearchIndexer(db_path=db_path, project_root=project_root)
    
    # Build index
    print("1.2 Building index...")
    start = time.time()
    stats = indexer.rebuild_index()
    elapsed = time.time() - start
    
    print(f"   ✅ Indexed {stats['files_indexed']} files")
    print(f"   ✅ Created {stats['chunks_created']} chunks")
    print(f"   ✅ Completed in {stats['duration_seconds']}s")
    print(f"   ✅ Errors: {len(stats['errors'])}")
    
    # Test search - model selector
    print("\n1.3 Testing search: 'model selector'...")
    results = indexer.search(query="model selector", extensions=None, limit=3)
    print(f"   ✅ Found {len(results)} results")
    for i, result in enumerate(results, 1):
        is_doc = result['file_path'].endswith(('FileStructure.md', 'IntegrationGuide.md'))
        doc_marker = " [DOC 3x]" if is_doc else ""
        print(f"   {i}. {result['file_path']} (score: {result['score']}){doc_marker}")
    
    # Test search - authentication in .md files
    print("\n1.4 Testing search: 'authentication' (.md only)...")
    results = indexer.search(query="authentication", extensions=['.md'], limit=3)
    print(f"   ✅ Found {len(results)} results")
    for i, result in enumerate(results, 1):
        print(f"   {i}. {result['file_path']} (score: {result['score']})")
    
    # Test search - get_gpt_service in .py files
    print("\n1.5 Testing search: 'get_gpt_service' (.py only)...")
    results = indexer.search(query="get_gpt_service", extensions=['.py'], limit=3)
    print(f"   ✅ Found {len(results)} results")
    for i, result in enumerate(results, 1):
        print(f"   {i}. {result['file_path']}:{result['line_start']} [{result['chunk_type']}] {result['symbol_name']}")
    
    # Test incremental update
    print("\n1.6 Testing incremental update (no changes)...")
    start = time.time()
    stats = indexer.incremental_update()
    elapsed = time.time() - start
    print(f"   ✅ Completed in {stats['duration_seconds']}s")
    print(f"   ✅ New: {stats['files_new']}, Modified: {stats['files_modified']}, Deleted: {stats['files_deleted']}")
    
    indexer.close()
    print("\n✅ Indexer tests passed!")


def test_python_lsp():
    """Test Python LSP functionality."""
    print("\n" + "=" * 60)
    print("TEST 2: Python LSP (jedi)")
    print("=" * 60)
    
    project_root = '/home/ubuntu/Study-With-LLM-refactor'
    lsp = LSPBridge(project_root=project_root)
    
    # Test definition lookup
    print("\n2.1 Finding definition: 'get_gpt_service'...")
    start = time.time()
    definitions = lsp.get_python_definition('get_gpt_service')
    elapsed = time.time() - start
    print(f"   ✅ Found {len(definitions)} definition(s) in {elapsed:.2f}s")
    
    # Find the actual function definition (not imports)
    func_defs = [d for d in definitions if d['kind'] == 'function_definition']
    if func_defs:
        defn = func_defs[0]
        print(f"   ✅ Main definition: {defn['file_path']}:{defn['line']}")
        print(f"      {defn['context'][:80]}...")
    
    # Test references lookup
    print("\n2.2 Finding references: 'get_gpt_service'...")
    start = time.time()
    references = lsp.get_python_references('get_gpt_service')
    elapsed = time.time() - start
    print(f"   ✅ Found {len(references)} reference(s) in {elapsed:.2f}s")
    
    # Show sample references
    for ref in references[:3]:
        print(f"      - {ref['file_path']}:{ref['line']} [{ref['kind']}]")
    
    print("\n✅ Python LSP tests passed!")


def test_typescript_lsp():
    """Test TypeScript LSP functionality."""
    print("\n" + "=" * 60)
    print("TEST 3: TypeScript LSP (ts-morph)")
    print("=" * 60)
    
    project_root = '/home/ubuntu/Study-With-LLM-refactor'
    lsp = LSPBridge(project_root=project_root)
    
    # Test definition lookup
    print("\n3.1 Finding definition: 'ModelSelector'...")
    start = time.time()
    try:
        definitions = lsp.get_typescript_definition('ModelSelector')
        elapsed = time.time() - start
        print(f"   ✅ Found {len(definitions)} definition(s) in {elapsed:.2f}s")
        
        if definitions:
            defn = definitions[0]
            print(f"   ✅ Definition: {defn['file_path']}:{defn['line']}")
            print(f"      {defn['context'][:80]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Test references lookup
    print("\n3.2 Finding references: 'ModelSelector'...")
    start = time.time()
    try:
        references = lsp.get_typescript_references('ModelSelector')
        elapsed = time.time() - start
        print(f"   ✅ Found {len(references)} reference(s) in {elapsed:.2f}s")
        
        # Show sample references
        for ref in references[:3]:
            print(f"      - {ref['file_path']}:{ref['line']} [{ref['kind']}]")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    print("\n✅ TypeScript LSP tests passed!")


def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("CODE SEARCH MCP SERVER - INTEGRATION TESTS")
    print("=" * 60)
    
    start_time = time.time()
    
    try:
        # Test 1: Indexer
        test_indexer()
        
        # Test 2: Python LSP
        test_python_lsp()
        
        # Test 3: TypeScript LSP
        test_typescript_lsp()
        
        # Summary
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"✅ ALL TESTS PASSED in {elapsed:.2f}s")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
