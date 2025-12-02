"""Tome service layer for document retrieval and search.

This is the middle layer between MCP tools and storage. It handles:
- Sentinel value translation (INDEX)
- Result type wrapping (Success/NoResults)
- Business logic validation
- Section-based content reconstruction
"""

import logging
from uuid import UUID

from sensei.database import storage
from sensei.database.models import Section
from sensei.types import NoResults, SearchResult, Success, TOCEntry, ToolError

logger = logging.getLogger(__name__)

# Sentinel values for common document paths
PATH_SENTINELS = {
    "INDEX": "/llms.txt",
}


async def tome_get(
    domain: str,
    path: str,
    heading: str | None = None,
) -> Success[str] | NoResults:
    """Get document content from an ingested domain.

    Args:
        domain: The domain to fetch from (e.g., "llmstext.org")
        path: Document path, or sentinel value "INDEX" for /llms.txt.
              Any other path like "/hooks/useState"
        heading: Optional heading to get subtree for specific section

    Returns:
        Success[str] with document content, or NoResults if not found
    """
    # Translate sentinel values to actual paths
    actual_path = PATH_SENTINELS.get(path, path)

    # Ensure path starts with /
    if not actual_path.startswith("/"):
        actual_path = f"/{actual_path}"

    logger.debug(f"tome_get: domain={domain}, path={actual_path}, heading={heading}")

    sections = await storage.get_sections_by_document(domain, actual_path)
    if not sections:
        return NoResults()

    if heading:
        # Filter to subtree starting at the specified heading
        sections = _get_subtree(sections, heading)
        if not sections:
            return NoResults()

    # Concatenate section content in position order
    content = "\n\n".join(s.content for s in sections if s.content)
    return Success(content)


def _get_subtree(sections: list[Section], heading: str) -> list[Section]:
    """Extract a section and all its descendants from a flat list.

    Args:
        sections: Flat list of sections ordered by position
        heading: Heading text to find

    Returns:
        List of sections (the matching section + all descendants)
    """
    # Find the root section by heading
    root = next((s for s in sections if s.heading == heading), None)
    if not root:
        return []

    # Build set of IDs in subtree by traversing parent relationships
    subtree_ids = {root.id}
    # Keep adding children until no more are found
    changed = True
    while changed:
        changed = False
        for s in sections:
            if s.parent_section_id in subtree_ids and s.id not in subtree_ids:
                subtree_ids.add(s.id)
                changed = True

    # Return sections in original order (by position)
    return [s for s in sections if s.id in subtree_ids]


def _normalize_path_prefixes(paths: list[str] | None) -> list[str] | None:
    """Normalize path prefixes for LIKE queries.

    Ensures each path:
    - Starts with / (for consistent matching)
    - Ends with % (for prefix matching)

    Args:
        paths: Raw path prefixes from user (e.g., ["hooks", "/api"])

    Returns:
        Normalized LIKE patterns (e.g., ["/hooks%", "/api%"]) or None
    """
    if not paths:
        return None

    normalized = []
    for path in paths:
        prefix = path if path.startswith("/") else f"/{path}"
        # Add % for LIKE prefix matching if not already present
        if not prefix.endswith("%"):
            prefix = f"{prefix}%"
        normalized.append(prefix)
    return normalized


async def tome_search(
    domain: str,
    query: str,
    paths: list[str] | None = None,
    limit: int = 10,
) -> Success[list[SearchResult]] | NoResults:
    """Search sections within an ingested domain using full-text search.

    Args:
        domain: The domain to search (e.g., "llmstext.org")
        query: Natural language search query
        paths: Optional path prefixes to filter (e.g., ["/hooks"])
        limit: Maximum results to return

    Returns:
        Success[list[SearchResult]] with matching sections, or NoResults
        Each result includes heading_path breadcrumb (e.g., "API > Hooks > useState")

    Raises:
        ToolError: If query is empty
    """
    if not query or not query.strip():
        raise ToolError("Search query cannot be empty")

    logger.debug(f"tome_search: domain={domain}, query={query}, paths={paths}")

    # Normalize paths for LIKE pattern matching
    path_prefixes = _normalize_path_prefixes(paths)

    results = await storage.search_sections_fts(domain, query, path_prefixes, limit)
    if not results:
        return NoResults()

    return Success(results)


async def tome_toc(
    domain: str,
    path: str,
) -> Success[list[TOCEntry]] | NoResults:
    """Get table of contents for a document.

    Returns the heading hierarchy derived from the section tree,
    useful for navigation and understanding document structure.

    Args:
        domain: The domain to fetch from (e.g., "llmstext.org")
        path: Document path, or sentinel value INDEX for /llms.txt

    Returns:
        Success[list[TOCEntry]] with heading tree, or NoResults if not found
    """
    # Translate sentinel values to actual paths
    actual_path = PATH_SENTINELS.get(path, path)

    # Ensure path starts with /
    if not actual_path.startswith("/"):
        actual_path = f"/{actual_path}"

    logger.debug(f"tome_toc: domain={domain}, path={actual_path}")

    # Get section hierarchy data
    sections = await storage.get_sections_by_document(domain, actual_path)
    if not sections:
        return NoResults()

    # Build tree from flat list using parent_section_id relationships
    toc = _build_toc_tree(sections)
    if not toc:
        return NoResults()

    return Success(toc)


def _build_toc_tree(sections: list[Section]) -> list[TOCEntry]:
    """Build TOCEntry tree from sections.

    Args:
        sections: List of Section objects

    Returns:
        List of root TOCEntry objects with nested children
    """
    # Create nodes for all sections with headings
    nodes: dict[UUID, TOCEntry] = {}
    parent_map: dict[UUID, UUID | None] = {}

    for section in sections:
        if section.heading:  # Only include sections with headings
            nodes[section.id] = TOCEntry(heading=section.heading, level=section.level, children=[])
            parent_map[section.id] = section.parent_section_id

    # Build tree by linking children to parents
    root_entries: list[TOCEntry] = []

    for section_id, entry in nodes.items():
        parent_id = parent_map[section_id]
        if parent_id and parent_id in nodes:
            # Add as child of parent
            nodes[parent_id].children.append(entry)
        else:
            # Root-level entry
            root_entries.append(entry)

    return root_entries
