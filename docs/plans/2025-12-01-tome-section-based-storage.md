# Tome: Section-Based Storage Design

**Date:** 2025-12-01
**Status:** Approved
**Epic:** sensei-tome-sections

## Problem

PostgreSQL's tsvector has a hard limit of ~1MB. Large `llms-full.txt` files (e.g., crawlee.dev at 1.1MB) exceed this limit, causing silent failures during ingestion.

The deeper issue: we're treating structured markdown as a monolithic blob. A 1MB `llms-full.txt` isn't one document—it's a **container** of many logical sections organized by headings.

## Core Insight

**Documents are containers. Sections are the content.**

Markdown headings provide natural boundaries. The llms.txt standard itself organizes docs this way:
- `/llms.txt` = INDEX (table of contents)
- `/llms-full.txt` = FULL (sections concatenated)
- Individual linked docs = standalone pieces

When an agent searches for "useState hooks", it doesn't want 1MB of context—it wants the specific **section** about useState.

## Design

### Data Model

```
Document (container, no content)
├── id (UUID, PK)
├── domain (String, indexed)
├── url (String, unique)
├── path (String)
├── content_hash (String - hash of original raw content for change detection)
├── inserted_at, updated_at

Section (content lives here)
├── id (UUID, PK)
├── document_id (FK → Document, indexed)
├── parent_section_id (FK → Section, nullable - null for root sections)
├── heading (String, nullable - null for intro/root content before first heading)
├── level (Integer - 0=root, 1=h1, 2=h2, etc.)
├── content (Text - this section's markdown content)
├── position (Integer - global order in original document for reconstruction)
├── search_vector (TSVECTOR, computed on content - always fits!)
├── inserted_at, updated_at
```

### Adaptive Recursive Chunking

Chunk boundaries adapt to content, not vice versa. The algorithm:

```
chunk(content, parent_id=None, position_counter) -> list[Section]:
    if token_count(content) <= MAX_TOKENS:
        # Fits! Return as single section
        return [Section(content, parent_id, position=next(position_counter))]

    # Too big - split by top-level headings
    children = split_by_top_level_headings(content)

    if no children with headings:
        raise Error("Content exceeds limit with no heading boundaries")

    results = []
    for child in children:
        section = Section(
            heading=child.heading,
            level=child.level,
            content=child.intro,  # Content before any child headings
            parent_id=parent_id,
            position=next(position_counter)
        )
        results.append(section)
        # Recurse into child's body (content under child headings)
        results.extend(chunk(child.body, parent_id=section.id, position_counter))

    return results
```

**Example:** A document with varying section sizes:

```
Document: /llms-full.txt
├── h2: "Getting Started" (2k tokens) → ONE Section
├── h2: "API Reference" (50k tokens, too big!)
│   ├── h3: "Client" (3k tokens) → ONE Section
│   ├── h3: "Server" (30k tokens, still too big!)
│   │   ├── h4: "Routes" (4k tokens) → ONE Section
│   │   ├── h4: "Middleware" (5k tokens) → ONE Section
│   │   └── h4: "Handlers" (20k tokens, still too big!)
│   │       ├── h5: "Request" (8k tokens) → ONE Section
│   │       └── h5: "Response" (8k tokens) → ONE Section
```

### API

| Function | Purpose |
|----------|---------|
| `tome_toc(domain, path)` | Return heading structure derived from Section tree |
| `tome_get(domain, path)` | Return full document (all sections concatenated by position) |
| `tome_get(domain, path, heading)` | Return section + all descendants under that heading |
| `tome_search(domain, query, paths?)` | Search sections, return heading_path breadcrumb + ts_headline snippet |
| `tome_ingest(domain)` | Crawl and ingest domain's llms.txt |

### Key Queries

**Reconstruct full document:**
```sql
SELECT content FROM sections
WHERE document_id = ?
ORDER BY position
```

**Get section subtree (for tome_get with heading):**
```sql
WITH RECURSIVE subtree AS (
  SELECT * FROM sections WHERE document_id = ? AND heading = ?
  UNION ALL
  SELECT s.* FROM sections s
  JOIN subtree t ON s.parent_section_id = t.id
)
SELECT content FROM subtree ORDER BY position
```

**Derive heading_path breadcrumb:**
```sql
WITH RECURSIVE ancestors AS (
  SELECT id, heading, parent_section_id, 1 as depth
  FROM sections WHERE id = ?
  UNION ALL
  SELECT s.id, s.heading, s.parent_section_id, a.depth + 1
  FROM sections s
  JOIN ancestors a ON s.id = a.parent_section_id
)
SELECT string_agg(heading, ' > ' ORDER BY depth DESC)
FROM ancestors
WHERE heading IS NOT NULL
```

**Search with context:**
```sql
SELECT
  s.id,
  s.heading,
  d.url,
  d.path,
  ts_headline('english', s.content, query, 'MaxWords=50') as snippet,
  ts_rank(s.search_vector, query) as rank,
  -- heading_path derived via subquery or join
FROM sections s
JOIN documents d ON s.document_id = d.id
WHERE s.search_vector @@ websearch_to_tsquery('english', ?)
  AND d.domain = ?
ORDER BY rank DESC
LIMIT 10
```

### Migration Strategy

This is a breaking change to the data model. Strategy:

1. Create new `sections` table
2. Modify `documents` table (remove content, search_vector columns)
3. Re-ingest all domains to populate sections
4. Update service layer and MCP tools

Since tome data is ephemeral (can be re-crawled), we don't need data migration—just re-ingest after schema change.

## Error Handling

- **Content too large with no heading boundaries:** Raise `BrokenInvariant`. This is unexpected and needs human investigation. YAGNI—don't solve until we hit it.
- **Network errors during crawl:** Raise `TransientError` (already implemented)
- **Domain not ingested:** Return `NoResults` from tome_get/tome_search

## Benefits

1. **FTS always works** - sections are naturally sized by headings
2. **Better search results** - return relevant section with heading context, not 1MB blob
3. **Granular retrieval** - get full doc OR specific section subtree
4. **Agent-friendly** - smaller, focused results that fit context windows
5. **Natural TOC** - heading structure is derived from data

## Non-Goals

- Semantic/embedding-based chunking (keep it simple with token counting)
- LLM-based chunking decisions (token counting is sufficient)
- Handling leaf nodes that exceed limit (raise error, investigate if it happens)
