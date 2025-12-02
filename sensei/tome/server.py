"""FastMCP server for Tome documentation tools.

This is the edge layer that:
1. Validates and parses MCP tool inputs
2. Calls tome service functions
3. Formats outputs for MCP
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from sensei.tome.crawler import ingest_domain
from sensei.tome.service import tome_get as _tome_get
from sensei.tome.service import tome_search as _tome_search
from sensei.types import IngestResult, NoResults, SearchResult, Success

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(server):
    """Ensure database is ready before handling requests."""
    from sensei.database.local import ensure_db_ready

    await ensure_db_ready()
    yield


# ─────────────────────────────────────────────────────────────────────────────
# FastMCP Server
# ─────────────────────────────────────────────────────────────────────────────

tome = FastMCP(name="tome", lifespan=lifespan)


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


@tome.tool
async def get(
    domain: Annotated[str, Field(description="Domain to fetch from (e.g., 'llmstext.org')")],
    path: Annotated[
        str,
        Field(description="Document path, or 'INDEX' for /llms.txt"),
    ],
) -> str:
    """Get documentation from an ingested llms.txt domain.

    Use this to retrieve specific documents from domains you've previously ingested.
    Start with path="INDEX" to see the table of contents, then fetch specific docs.

    Examples:
        - domain="llmstext.org", path="INDEX" - get the llms.txt table of contents
        - domain="llmstext.org", path="/hooks/useState" - get a specific document
    """
    match await _tome_get(domain, path):
        case Success(content):
            return content
        case NoResults():
            return f"Document not found: {domain}{path if path.startswith('/') else '/' + path}"


@tome.tool
async def search(
    domain: Annotated[str, Field(description="Domain to search (e.g., 'llmstext.org')")],
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
        - domain="llmstext.org", query="useState" - search all docs for useState
        - domain="llmstext.org", query="state management", paths=["/hooks"] - search only hooks docs
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
        Field(description="Domain to ingest (e.g., 'llmstext.org')"),
    ],
    max_depth: Annotated[
        int,
        Field(description="Maximum link depth to follow (0=only llms.txt)", ge=0, le=5),
    ] = 3,
) -> str:
    """Ingest a domain's llms.txt documentation into the knowledge base.

    Fetches /llms.txt, parses links, and crawls all same-domain linked
    documents up to max_depth.

    Use this before searching a domain for the first time.

    Examples:
        - domain="llmstext.org" - ingest React documentation
        - domain="fastapi.tiangolo.com", max_depth=1 - shallow crawl
    """
    match await ingest_domain(domain, max_depth):
        case Success(result):
            return _format_ingest_result(result)


def _format_exception(e: Exception) -> str:
    """Format an exception for display, showing type and message."""
    return f"{type(e).__name__}: {e}"


def _format_ingest_result(result: IngestResult) -> str:
    """Format ingest result based on success/failure status.

    Any failures = overall failure, regardless of documents added.
    Zero documents with only warnings = failure (nothing useful ingested).
    """
    # Any failures = FAILURE
    if result.failures:
        failure_msgs = [_format_exception(e) for e in result.failures[:3]]
        failure_summary = "; ".join(failure_msgs)
        if len(result.failures) > 3:
            failure_summary += f" (+{len(result.failures) - 3} more)"
        docs_note = f" Got {result.documents_added} documents." if result.documents_added > 0 else ""
        return f"FAILED: {result.domain} - {failure_summary}{docs_note}"

    # Zero documents (even with only warnings) = failure
    if result.documents_added == 0:
        if result.warnings:
            return f"No documents found for {result.domain} ({len(result.warnings)} skipped)"
        return f"No documents found for {result.domain}"

    # Success with warnings
    if result.warnings:
        return f"Ingested {result.domain}: {result.documents_added} documents ({len(result.warnings)} skipped)"

    # Clean success
    return f"Ingested {result.domain}: {result.documents_added} documents"


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
