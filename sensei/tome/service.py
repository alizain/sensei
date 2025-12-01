"""Tome service layer for document retrieval and search.

This is the middle layer between MCP tools and storage. It handles:
- Sentinel value translation (INDEX, FULL)
- Result type wrapping (Success/NoResults)
- Business logic validation
- Section-based content reconstruction
"""

import logging
from uuid import UUID

from sensei.database import storage
from sensei.types import NoResults, SearchResult, Success, TOCEntry, ToolError

logger = logging.getLogger(__name__)

# Sentinel values for common document paths
PATH_SENTINELS = {
	"INDEX": "/llms.txt",
	"FULL": "/llms-full.txt",
}


async def tome_get(
	domain: str,
	path: str,
	heading: str | None = None,
) -> Success[str] | NoResults:
	"""Get document content from an ingested domain.

	Args:
	    domain: The domain to fetch from (e.g., "react.dev")
	    path: Document path, or sentinel values:
	          - "INDEX" for /llms.txt (table of contents)
	          - "FULL" for /llms-full.txt (complete docs)
	          - Any other path like "/hooks/useState"
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

	if heading:
		# Get specific section subtree
		sections = await storage.get_section_subtree_by_heading(domain, actual_path, heading)
	else:
		# Get all sections for full document
		sections = await storage.get_sections_by_document(domain, actual_path)

	if not sections:
		return NoResults()

	# Concatenate section content in position order
	content = "\n\n".join(s.content for s in sections if s.content)
	return Success(content)


async def tome_search(
	domain: str,
	query: str,
	paths: list[str] | None = None,
	limit: int = 10,
) -> Success[list[SearchResult]] | NoResults:
	"""Search sections within an ingested domain using full-text search.

	Args:
	    domain: The domain to search (e.g., "react.dev")
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

	results = await storage.search_sections_fts(domain, query, paths, limit)
	if results:
		return Success(results)
	return NoResults()


async def tome_toc(
	domain: str,
	path: str,
) -> Success[list[TOCEntry]] | NoResults:
	"""Get table of contents for a document.

	Returns the heading hierarchy derived from the section tree,
	useful for navigation and understanding document structure.

	Args:
	    domain: The domain to fetch from (e.g., "react.dev")
	    path: Document path, or sentinel values (INDEX, FULL)

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
	sections = await storage.get_sections_for_toc(domain, actual_path)
	if not sections:
		return NoResults()

	# Build tree from flat list using parent_section_id relationships
	toc = _build_toc_tree(sections)
	if not toc:
		return NoResults()

	return Success(toc)


def _build_toc_tree(
	sections: list[tuple[UUID, UUID | None, str | None, int]],
) -> list[TOCEntry]:
	"""Build TOCEntry tree from flat section data.

	Args:
	    sections: List of (id, parent_section_id, heading, level) tuples

	Returns:
	    List of root TOCEntry objects with nested children
	"""
	# Create nodes for all sections with headings
	nodes: dict[UUID, TOCEntry] = {}
	parent_map: dict[UUID, UUID | None] = {}

	for section_id, parent_id, heading, level in sections:
		if heading:  # Only include sections with headings
			nodes[section_id] = TOCEntry(heading=heading, level=level, children=[])
			parent_map[section_id] = parent_id

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
