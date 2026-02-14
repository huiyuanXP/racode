# RACode

**Retrieval-Augmented Code Search** — BM25 + LSP intelligence for large codebases.

A Model Context Protocol (MCP) server that provides intelligent code search for Claude Code. Unlike traditional RAG (which uses embeddings), RACode uses **BM25 ranking** for precise keyword matching and **LSP integration** for compiler-grade symbol resolution — all running locally with zero external API calls.

## Why Choose This MCP?

### The 10K+ File Problem

When working with large codebases (10,000+ files), spawning a new agent to make code changes creates a token crisis:

**Traditional Approaches Fail:**

1. **Grep/Glob Exploration** — Agent searches files pattern-by-pattern, reading dozens of files to understand structure. For a 10K-file project, this burns through thousands of tokens before writing a single line of code.

2. **Massive README Documentation** — Putting all file structures and integration guides in a single README.md creates a different problem: the documentation itself becomes 5K+ lines, consuming huge context just to load, filled with irrelevant details for the current task.

3. **RAG (Retrieval-Augmented Generation)** — Embedding-based semantic search sounds modern, but it's fundamentally wrong for code:
   - Embeddings capture semantic similarity, but code similarity ≠ code relevance
   - Two completely different functions can have similar vector representations
   - External embedding APIs mean sending your private code outside
   - RAG can't understand syntax, scoping, or symbol relationships

### The Solution: BM25 + LSP Architecture

This MCP uses **BM25 (Best Matching 25)**, a battle-tested information retrieval algorithm, combined with **LSP (Language Server Protocol)** for compiler-grade symbol resolution.

**Why BM25 Works for Code:**

- **Exact keyword matching** — When you search for `ModelSelector`, you want files containing that exact identifier, not semantically similar text
- **Term frequency + inverse document frequency** — Rare terms (like your custom class names) rank higher than common terms (like `function` or `import`)
- **Fast and local** — SQLite FTS5 runs on your machine, no external API calls, no privacy concerns
- **Document boost** — 3x ranking multiplier for curated documentation (`FileStructure.md`, `IntegrationGuide.md`) ensures high-quality explanations surface first

**Why LSP Beats Pattern Matching:**

- **Compiler-grade accuracy** — Understands scopes, imports, and type relationships
- **Find all references** — Not just text matches, but actual usage sites resolved by syntax analysis
- **Jump to definition** — Precise location, even across file boundaries
- **Language-specific** — jedi for Python, ts-morph for TypeScript, each using the language's own compiler infrastructure

**The Result:**

Instead of an agent reading 50 files to understand your auth module, it:
1. Searches `code_search_search(query="authentication", extensions=".md")` → finds `FileStructure.md` ranked first (3x boost) → reads 1 file
2. Calls `code_search_get_definition(symbol="login", language="python")` → jumps directly to line 42 of `auth_service.py`
3. Calls `code_search_get_references(symbol="login", language="python")` → sees 8 call sites across the codebase

**Token savings: ~90% reduction.** From thousands of tokens exploring, to dozens of tokens with precise results.

**All data stays local.** Your code never leaves your machine. The `.code_search.db` SQLite database lives in your project directory, indexing is instant (~17ms incremental updates), and BM25 ranking happens in-process.

### Designed for Structured Documentation

This MCP is optimized for projects that maintain folder-level documentation:
- **FileStructure.md** — Describes each file's purpose, key functions, and dependencies
- **IntegrationGuide.md** — Shows how to use the folder's functionality from other modules

When you follow this convention, the MCP's 3x document boost ensures agents read curated explanations before raw source code, dramatically improving context quality per token spent.

## What It Does

| Tool | Purpose |
|------|---------|
| `code_search_search` | Full-text search with BM25 ranking. Documentation files (`FileStructure.md`, `IntegrationGuide.md`) get a 3x ranking boost. |
| `code_search_get_definition` | Jump to the definition of a function, class, or component via LSP. |
| `code_search_get_references` | Find all usages of a symbol across the codebase via LSP. |
| `code_search_rebuild_index` | Force a full re-index (rarely needed; index auto-updates before each search). |

### Key Features

- **Incremental indexing** -- only re-indexes files that changed (based on mtime), so searches are always up-to-date with near-zero overhead.
- **Semantic chunking** -- splits files into meaningful units: Markdown by headings, Python by functions/classes, TypeScript by exports.
- **Documentation boost** -- `FileStructure.md` and `IntegrationGuide.md` rank 3x higher, so structural documentation surfaces first.
- **Markdown trimming** -- for `.md` results, returns ~10 lines around the keyword match instead of the full chunk, reducing noise.
- **LSP integration** -- Python symbol lookup via [jedi](https://github.com/davidhalter/jedi); TypeScript via [ts-morph](https://github.com/dsherret/ts-morph).

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for TypeScript symbol lookup)
- Claude Code CLI

### Installation

```bash
# 1. Clone RACode repository
git clone https://github.com/huiyuanXP/racode.git
cd racode

# 2. Install dependencies
pip install -r requirements.txt
npm install

# 3. Test the server (optional)
python test_integration.py -v
```

### Configuration

Add RACode to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "racode": {
      "command": "python",
      "args": ["/path/to/racode/server.py", "--project-root", "."]
    }
  }
}
```

Or use a relative path if you copied RACode into your project:

```json
{
  "mcpServers": {
    "racode": {
      "command": "python",
      "args": ["mcp/racode/server.py", "--project-root", "."]
    }
  }
}
```

### Verification

```bash
claude mcp list
# Should show: racode (connected)
```

---

## Built for SkipLec

RACode was originally developed for [**SkipLec**](https://github.com/huiyuanXP/skiplec) — an AI-powered study platform that transforms lectures into structured notes.

SkipLec's codebase (10K+ files) needed intelligent code navigation, which led to RACode's creation. The project showcases RACode's real-world usage with:

- **Structured documentation** — FileStructure.md and IntegrationGuide.md in every folder, optimized for RACode's 3x document boost
- **Zero-config setup** — Clone SkipLec and RACode works immediately via git subtree integration
- **90% token savings** — Agents explore the codebase using RACode instead of Grep/Glob

**See RACode in action**: Check out [SkipLec's codebase](https://github.com/huiyuanXP/skiplec) to see how a real project organizes documentation for RACode's BM25 search.

**⭐ If RACode helps your project, consider starring [SkipLec](https://github.com/huiyuanXP/skiplec) to support the project that made it possible!**

## Recommended Setup

To get the most out of this MCP, configure these three things: a **rule file**, a **hook**, and **folder-level documentation**.

---

### 1. Rule File (Prompt for Claude Code)

Create `.claude/rules/code-search.md` to instruct Claude Code to prefer MCP tools over built-in Grep/Glob:

```markdown
# Code Search MCP

## Tool Priority for Code Exploration

Use Code Search MCP **before** Grep/Glob when exploring code:

1. **`code_search_search`** -- Full-text search with BM25 ranking
   - Documentation files (FileStructure.md, IntegrationGuide.md) get 3x boost
   - Params: `query` (keywords), `extensions` (.md/.py/.tsx/*), `limit` (default 5)

2. **`code_search_get_definition`** -- Jump to symbol definition via LSP
   - Params: `symbol` (name), `language` (python/typescript)

3. **`code_search_get_references`** -- Find all usages of a symbol via LSP
   - Params: `symbol` (name), `language` (python/typescript)

4. **`code_search_rebuild_index`** -- Force full re-index (rarely needed)

## When to Use Code Search vs Grep/Glob

| Task | Use |
|------|-----|
| Find where a function/component is defined | `code_search_get_definition` |
| Find all usages of a symbol | `code_search_get_references` |
| Understand a feature or module | `code_search_search` with `.md` |
| Find implementation code | `code_search_search` with `.py`/`.tsx` |
| Exact regex pattern match | Grep (fallback) |
| Find files by name/glob | Glob (fallback) |

## Typical Workflow

    code_search_search(query="feature name", extensions=".md")   -- find docs
    code_search_get_definition(symbol="SymbolName", language=...) -- jump to source
    code_search_get_references(symbol="SymbolName", language=...) -- find usages
    Read specific file                                            -- read full context
```

---

### 2. Hook (Gentle Reminder)

Add a PreToolUse hook in `.claude/hooks/hooks.json` to remind Claude Code about MCP tools when it uses Grep/Glob for code exploration:

```json
{
  "matcher": "tool == \"Grep\" || tool == \"Glob\"",
  "hooks": [
    {
      "type": "command",
      "command": "node -e \"let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const i=JSON.parse(d);const p=(i.tool_input?.pattern||i.tool_input?.query||'').toLowerCase();const kw=['function','class','interface','import','export','component','usestate','useeffect','def ','service','handler','.tsx','.ts','.py'];if(kw.some(k=>p.includes(k))){console.error('[Hook] TIP: Consider code_search_search / code_search_get_definition / code_search_get_references for code exploration')}console.log(d)})\""
    }
  ],
  "description": "Suggest Code Search MCP when Grep/Glob is used for code exploration"
}
```

This hook checks the search pattern for code-related keywords (like `function`, `class`, `component`) and prints a tip to stderr suggesting the MCP tools instead. It does not block execution.

---

### 3. Folder-Level Documentation (FileStructure.md)

This MCP is designed to work with structured folder documentation. When you maintain `FileStructure.md` and `IntegrationGuide.md` files in each folder, the MCP indexes them with a **3x ranking boost**, making project knowledge instantly searchable.

#### Recommended Structure

```
your-project/
  backend/
    app/
      FileStructure.md      <-- describes each file in app/
      IntegrationGuide.md   <-- how to use app/ from other modules
      auth/
        FileStructure.md
        IntegrationGuide.md
  frontend/
    components/
      FileStructure.md
      IntegrationGuide.md
```

#### FileStructure.md Format

Each file in the folder gets a heading with its purpose, key functions, and dependencies:

```markdown
# backend/app/

### auth_service.py
Authentication service handling login, registration, and token management.

**Key Functions:**
- `login(email, password)` -- Validates credentials and returns JWT token
- `register(user_data)` -- Creates new user account
- `verify_token(token)` -- Validates and decodes JWT

**Dependencies**: `models.py`, `database.py`, `utils/crypto.py`

### file_parser.py
Parses uploaded files (PDF, DOCX, TXT) into structured text for LLM processing.

**Key Functions:**
- `parse_file(file_path)` -- Detects format and extracts text
- `chunk_text(text, max_tokens)` -- Splits text into LLM-sized chunks

**Dependencies**: `PyPDF2`, `python-docx`
```

#### IntegrationGuide.md Format

Describes how other parts of the codebase should use this folder's functionality:

```markdown
# backend/app/ Integration Guide

### Authentication
```python
from app.auth_service import login, verify_token

# Login and get token
result = login("user@example.com", "password")
token = result["token"]

# Verify token in middleware
user = verify_token(request.headers["Authorization"])
```

### When to Use
- Use `auth_service` for all authentication -- never access user table directly
- Use `file_parser` for file uploads -- it handles format detection automatically

### When NOT to Use
- Don't import internal helpers like `_hash_password` -- use the public API
```

#### Why This Matters

Without documentation files, Claude Code must grep through raw source code to understand your project. With `FileStructure.md` and `IntegrationGuide.md`:

1. **Faster context loading** -- Claude reads a 50-line doc summary instead of 500 lines of source code
2. **Better search ranking** -- the 3x boost ensures structural docs surface before random code matches
3. **Consistent understanding** -- documentation captures intent and usage patterns that code alone does not convey

## Performance

Tested on a real codebase (490 files, 3845 chunks):

| Operation | Time |
|-----------|------|
| First-time indexing | ~0.8s |
| Incremental update (no changes) | ~17ms |
| Incremental update (with changes) | ~200ms |
| Search query | <100ms |
| Python definition (jedi) | ~4.4s |
| Python references (jedi) | ~2.6s |
| TypeScript definition (ts-morph) | ~0.9s |
| TypeScript references (ts-morph) | ~1.9s |

## Tool Examples

### code_search_search

Search documentation for a feature:

```json
{
  "query": "model selector",
  "extensions": ".md",
  "limit": 5
}
```

Search Python source code:

```json
{
  "query": "get_gpt_service",
  "extensions": ".py"
}
```

Search all files:

```json
{
  "query": "authentication",
  "extensions": "*",
  "limit": 10
}
```

### code_search_get_definition

```json
{
  "symbol": "ModelSelector",
  "language": "typescript"
}
```

Returns:

```json
{
  "results": [
    {
      "file_path": "frontend/components/ModelSelector.tsx",
      "line": 26,
      "column": 0,
      "context": "export function ModelSelector({",
      "kind": "function_definition"
    }
  ]
}
```

### code_search_get_references

```json
{
  "symbol": "get_gpt_service",
  "language": "python"
}
```

Returns all files and line numbers where the symbol is used, with surrounding context.

## Use Cases

### Understand a new codebase

```
1. code_search_search(query="authentication", extensions=".md")    -- find docs
2. code_search_search(query="authentication login", extensions=".py") -- find code
3. code_search_get_definition(symbol="login", language="python")    -- jump to source
4. code_search_get_references(symbol="login", language="python")    -- find all callers
```

### Safely refactor a function

```
1. code_search_get_definition(symbol="get_gpt_service", language="python")  -- find it
2. code_search_get_references(symbol="get_gpt_service", language="python")  -- find all usages
3. Review each reference location before renaming
```

### Understand component integration

```
1. code_search_search(query="ModelSelector integration", extensions=".md")    -- docs first
2. code_search_get_definition(symbol="ModelSelector", language="typescript")  -- source
3. code_search_get_references(symbol="ModelSelector", language="typescript") -- all usages
```

## Architecture

```
mcp/
  server.py          -- MCP server entry point (FastMCP, 4 tool handlers)
  indexer.py         -- SQLite FTS5 indexer with incremental updates
  chunker.py         -- Semantic file chunking (Markdown/Python/TypeScript)
  lsp_bridge.py      -- LSP integration (jedi for Python, ts-morph for TS)
  ts_helper.js       -- Node.js subprocess for TypeScript symbol lookup
  test_integration.py -- Integration tests
  requirements.txt   -- Python dependencies (mcp, jedi)
  package.json       -- Node.js dependencies (ts-morph)
```

### Data Flow

```
Search query
  --> server.py (validate input, trigger incremental update)
  --> indexer.py (FTS5 MATCH with BM25 ranking + doc boost)
  --> return ranked results (markdown trimmed to ~10 lines around match)

Symbol lookup
  --> server.py (validate input)
  --> lsp_bridge.py --> jedi (Python) or ts_helper.js (TypeScript)
  --> return definition/reference locations with context
```

### Database Schema

```sql
-- File metadata for incremental updates (mtime comparison)
CREATE TABLE file_meta (
    file_path TEXT PRIMARY KEY,
    mtime_ns  INTEGER NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0
);

-- FTS5 virtual table with external content mode
CREATE VIRTUAL TABLE chunks USING fts5(
    file_path, chunk_type, symbol_name, content,
    line_start UNINDEXED, line_end UNINDEXED, is_doc_file UNINDEXED,
    content='chunks_content', content_rowid='rowid'
);

-- Search with document boost
SELECT *,
       rank * CASE WHEN is_doc_file = 1 THEN 3.0 ELSE 1.0 END AS score
FROM chunks
WHERE chunks MATCH ?
ORDER BY score
LIMIT ?;
```

### Generated Files

These are created automatically and should be gitignored:

- `.code_search.db` -- SQLite FTS5 database (auto-generated at project root)
- `node_modules/` -- ts-morph and dependencies
- `__pycache__/` -- Python bytecode cache

## Running Tests

```bash
cd mcp/
python test_integration.py -v
```

## Configuration Options

| Argument | Default | Description |
|----------|---------|-------------|
| `--project-root` | (required) | Root directory to index |
| `--db-path` | `<project-root>/.code_search.db` | Custom database location |

### Indexing Behavior

- **Skipped directories**: `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`, `build`, `.next`, `.cache`, `coverage`
- **Indexed extensions**: `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.toml`
- **Search defaults**: 5 results, `.md` extension filter, BM25 ranking

## Troubleshooting

### "jedi is not installed"

```bash
pip install jedi
```

### "TypeScript helper not found"

```bash
cd mcp/ && npm install
```

### No search results

1. Try broader keywords
2. Try `extensions="*"` to search all file types
3. Run `code_search_rebuild_index` to force a fresh index

### Slow LSP queries

LSP scans all files of the target language. This is expected. Use `code_search_search` first to narrow down, then LSP for precise lookup.

## License

MIT
