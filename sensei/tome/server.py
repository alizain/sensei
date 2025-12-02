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

from sensei.cli import run_server
from sensei.database import storage
from sensei.tome.crawler import ingest_domain
from sensei.tome.service import tome_get as _tome_get
from sensei.tome.service import tome_search as _tome_search
from sensei.types import NoResults, SearchResult, Success

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
# Auto-ingest Helper
# ─────────────────────────────────────────────────────────────────────────────


async def _ensure_domain_ingested(domain: str) -> str | None:
    """Ensure domain has been ingested, auto-ingesting if needed.

    This is edge-layer orchestration: check if we have docs for the domain,
    ingest if not, and return an error message or None if ready.

    Args:
        domain: The domain to check/ingest (e.g., 'react.dev')

    Returns:
        None if domain is ready (has docs), or error message string if not
    """
    if await storage.has_active_documents(domain):
        return None  # Domain already ingested

    logger.info(f"Auto-ingesting unknown domain: {domain}")
    match await ingest_domain(domain):
        case Success(result) if result.failures:
            # Ingest had failures - return detailed error
            failure_msg = _format_exception(result.failures[0])
            return f"Could not ingest {domain}: {failure_msg}"
        case Success(result) if result.documents_added == 0:
            # Ingest succeeded but no docs - log warning, return message
            logger.warning(f"Auto-ingest succeeded but 0 documents: {domain}")
            return f"No documents found for {domain}"
        case Success(_):
            # Ingest succeeded with docs
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


@tome.tool
async def get(
    domain: Annotated[str, Field(description="Domain to fetch from (e.g., 'react.dev')")],
    path: Annotated[
        str,
        Field(description="Document path, or 'INDEX' for /llms.txt"),
    ],
) -> str:
    """Get documentation from an llms.txt domain.

    Use this to retrieve specific documents from domains you've previously ingested.
    Start with path="INDEX" to see the table of contents, then fetch specific docs.

    Examples:
        - domain="react.dev", path="INDEX" - get the llms.txt table of contents
        - domain="react.dev", path="/hooks/useState" - get a specific document
    """
    # Auto-ingest if domain is unknown
    if error := await _ensure_domain_ingested(domain):
        return error

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
    """Search documentation within an llms.txt domain.

    Uses full-text search to find relevant documentation. Results include
    snippets with highlighted search terms and relevance ranking.

    Examples:
        - domain="react.dev", query="useState" - search all docs for useState
        - domain="react.dev", query="state management", paths=["/hooks"] - search only hooks docs
    """
    # Auto-ingest if domain is unknown
    if error := await _ensure_domain_ingested(domain):
        return error

    match await _tome_search(domain, query, paths or None, limit):
        case Success(results):
            return _format_search_results(results)
        case NoResults():
            return f"No results for '{query}' in {domain}"


# ─────────────────────────────────────────────────────────────────────────────
# Formatters
# ─────────────────────────────────────────────────────────────────────────────


def _format_exception(e: Exception) -> str:
    """Format an exception for display, showing type and message."""
    return f"{type(e).__name__}: {e}"


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


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Entry point for `uv run tome` or `python -m sensei.tome`."""
    run_server(tome, "tome", "Tome documentation MCP server")
