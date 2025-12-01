"""FastMCP server for Tome documentation tools.

This is the edge layer that:
1. Validates and parses MCP tool inputs
2. Calls tome service functions
3. Formats outputs for MCP
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from sensei.tome.crawler import ingest_domain
from sensei.tome.service import tome_get as _tome_get
from sensei.tome.service import tome_search as _tome_search
from sensei.types import NoResults, SearchResult, Success

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FastMCP Server
# ─────────────────────────────────────────────────────────────────────────────

tome = FastMCP(name="tome")


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


@tome.tool
async def get(
	domain: Annotated[str, Field(description="Domain to fetch from (e.g., 'react.dev')")],
	path: Annotated[
		str,
		Field(
			description="Document path, or 'INDEX' for /llms.txt, 'FULL' for /llms-full.txt"
		),
	],
) -> str:
	"""Get documentation from an ingested llms.txt domain.

	Use this to retrieve specific documents from domains you've previously ingested.
	Start with path="INDEX" to see the table of contents, then fetch specific docs.

	Examples:
	    - domain="react.dev", path="INDEX" - get the llms.txt table of contents
	    - domain="react.dev", path="FULL" - get the complete llms-full.txt
	    - domain="react.dev", path="/hooks/useState" - get a specific document
	"""
	match await _tome_get(domain, path):
		case Success(content):
			return content
		case NoResults():
			return f"Document not found: {domain}{path if path.startswith('/') else '/' + path}"


@tome.tool
async def search(
	domain: Annotated[str, Field(description="Domain to search (e.g., 'react.dev')")],
	query: Annotated[str, Field(description="Natural language search query")],
	paths: Annotated[
		list[str],
		Field(description="Path prefixes to search within (empty = all paths)"),
	] = [],
	limit: Annotated[int, Field(description="Maximum results", ge=1, le=50)] = 10,
) -> str:
	"""Search documentation within an ingested llms.txt domain.

	Uses full-text search to find relevant documentation. Results include
	snippets with highlighted search terms and relevance ranking.

	Examples:
	    - domain="react.dev", query="useState" - search all docs for useState
	    - domain="react.dev", query="state management", paths=["/hooks"] - search only hooks docs
	"""
	match await _tome_search(domain, query, paths or None, limit):
		case Success(results):
			return _format_search_results(results)
		case NoResults():
			return f"No results for '{query}' in {domain}"


@tome.tool
async def ingest(
	domain: Annotated[
		str,
		Field(description="Domain to ingest (e.g., 'react.dev')"),
	],
	max_depth: Annotated[
		int,
		Field(description="Maximum link depth to follow (0=only llms.txt)", ge=0, le=5),
	] = 3,
) -> str:
	"""Ingest a domain's llms.txt documentation into the knowledge base.

	Fetches /llms.txt and /llms-full.txt (if available), parses links,
	and crawls all same-domain linked documents up to max_depth.

	Use this before searching a domain for the first time.

	Examples:
	    - domain="react.dev" - ingest React documentation
	    - domain="fastapi.tiangolo.com", max_depth=1 - shallow crawl
	"""
	match await ingest_domain(domain, max_depth):
		case Success(result):
			return (
				f"Ingested {result.domain}: "
				f"{result.documents_added} added, "
				f"{result.documents_updated} updated, "
				f"{result.documents_skipped} unchanged"
				+ (f", {len(result.errors)} errors" if result.errors else "")
			)


def _format_search_results(results: list[SearchResult]) -> str:
	"""Format search results for display."""
	if not results:
		return "No results found"

	lines = []
	for i, r in enumerate(results, 1):
		lines.append(f"## {i}. {r.path}")
		lines.append(f"**URL:** {r.url}")
		lines.append(f"**Relevance:** {r.rank:.3f}")
		lines.append(f"\n{r.snippet}\n")

	return "\n".join(lines)
