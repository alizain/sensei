# Codebase Understanding Design

**Date**: 2025-12-18
**Status**: Draft (checkpointed from brainstorming)

## Goal

Build semantic understanding of codebases that enables:
1. **Sensei query enhancement** — Better documentation answers by knowing code structure
2. **Documentation tool** — Write external-facing docs grounded in actual code
3. **Scout intelligence** — Baseline codebase understanding for any repo

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Sensei Semantic Layer                  │
│  • AI-generated summaries (at query time)           │
│  • Natural language Q&A about code                  │
│  • Documentation generation assistance              │
└─────────────────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
┌─────────────────────┐       ┌─────────────────────┐
│   Scout Indexer     │       │  Sourcegraph MCP    │
│   (built-in)        │       │  (enterprise)       │
│                     │       │                     │
│  • Tree-sitter AST  │       │  • SCIP index       │
│  • Symbol graph     │       │  • Cross-repo refs  │
│  • Lightweight      │       │  • Battle-tested    │
└─────────────────────┘       └─────────────────────┘
```

Enterprise customers can connect Sourcegraph via MCP. Scout provides baseline understanding for everyone else.

## Product Breakdown

| Component | Description | AI Involved? |
|-----------|-------------|--------------|
| **A: Scout Structural Index** | Tree-sitter parsing, symbol graph, relationships, PageRank | No (deterministic) |
| **B: Sensei Integration** | Feed A into Sensei's query pipeline | Yes (at query time) |
| **C: Documentation Tool** | Help write external-facing docs using A | Yes (at query time) |

**Decision**: A is pure deterministic structure. AI interpretation happens at query time in B/C.

## Scout Structural Index (A)

### What It Produces

| Entity | Fields |
|--------|--------|
| **Symbol** | name, kind (function/class/method), file, line, signature, docstring (if present) |
| **Relationship** | source_symbol, target_symbol, type (calls/imports/inherits/references) |
| **File** | path, hash (for change detection), language |

Plus **PageRank scores** on symbols for importance ranking.

### Storage

SQLite per-repo (like beads pattern):
```
.scout/
  index.db      # symbols, relationships, files
  meta.json     # repo root, last indexed commit
```

### Implementation Approach

**Recommended: Build on RepoMapper**
- pdavis68/RepoMapper is MIT-licensed, standalone extraction of Aider's approach
- Already has tree-sitter + PageRank
- Swap text output for SQLite storage
- Add incremental updates

Alternative: Build from scratch with py-tree-sitter-languages (more control, more work).

### Proposed API (Scout tools)

```
scout_index(repo_path)            # Build/update index
scout_symbols(query, kind, limit) # Search symbols
scout_references(symbol_id)       # What references this?
scout_dependents(symbol_id)       # What does this depend on?
scout_important(limit)            # Top PageRank symbols
scout_file_symbols(file_path)     # All symbols in a file
```

## Research Summary

### Tools Analyzed

| Tool | Core Output | Key Differentiator |
|------|-------------|-------------------|
| **Aider RepoMap** | Text map with signatures | Fits LLM context, PageRank ranking |
| **Greptile** | Graph + blast radius | PR review focus, catches bugs via relationships |
| **Swimm** | Linked docs ↔ code | Docs stay synced as code evolves |
| **Windsurf Codemaps** | Visual hierarchical maps | Interactive chat about system design |
| **Google CodeWiki** | Living wiki + diagrams | Auto-updates, architecture/sequence diagrams |
| **DeepWiki** | Natural language Q&A | "How does auth work in this repo?" |
| **Sourcegraph** | SCIP index, cross-repo refs | Enterprise-grade, battle-tested |

### Common Technical Foundation

All approaches share:
1. **Tree-sitter AST parsing** → Extract symbols
2. **Graph construction** → Nodes (files/symbols), edges (calls/imports)
3. **Ranking algorithm** → PageRank to find "important" code
4. **AI enhancement** → Generate summaries, answer questions

### Existing Scout Code

`sensei/scout/repomap.py` has a disabled Aider wrapper due to openai version conflicts:
- aider-chat pins openai==1.99.1
- pydantic-ai requires openai>=1.107.2

RepoMapper (standalone) avoids this dependency issue.

## Open Questions

1. **Incremental updates**: How to detect file changes and update index efficiently?
2. **Multi-language support**: Which languages to prioritize?
3. **Sourcegraph MCP**: Define the interface for enterprise integration
4. **B integration**: How exactly does Sensei query the index during documentation lookups?

## Next Steps

1. Evaluate RepoMapper for direct integration vs. extracting approach
2. Design SQLite schema for symbols/relationships
3. Prototype indexing on a test repo
4. Define MCP tools for querying the index
