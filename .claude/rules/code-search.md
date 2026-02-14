# RACode (Code Search MCP)

## Tool Priority for Code Exploration

Use RACode **before** Grep/Glob when exploring code:

1. **`code_search_search`** — Full-text search with BM25 ranking
   - Documentation files (FileStructure.md, IntegrationGuide.md) get 3x boost
   - Params: `query` (keywords), `extensions` (.md/.py/.tsx/*), `limit` (default 5)

2. **`code_search_get_definition`** — Jump to symbol definition via LSP
   - Params: `symbol` (name), `language` (python/typescript)

3. **`code_search_get_references`** — Find all usages of a symbol via LSP
   - Params: `symbol` (name), `language` (python/typescript)

4. **`code_search_rebuild_index`** — Force full re-index (rarely needed)

## When to Use Code Search vs Grep/Glob

| Task | Use |
|------|-----|
| Find where a function/component is defined | `code_search_get_definition` |
| Find all usages of a symbol | `code_search_get_references` |
| Understand a feature or module | `code_search_search` with `.md` |
| Find implementation code | `code_search_search` with `.py`/`.tsx` |
| Exact regex pattern match | Grep (fallback) |
| Find files by name/glob | Glob (fallback) |
| Search non-code content (logs, data) | Grep (fallback) |

## Typical Workflow

```
code_search_search(query="feature name", extensions=".md")   -- find docs
code_search_get_definition(symbol="SymbolName", language=...) -- jump to source
code_search_get_references(symbol="SymbolName", language=...) -- find usages
Read specific file                                            -- read full context
```
