"""FastMCP server for Kura cache tools.

This is the edge layer that:
1. Validates and parses MCP tool inputs
2. Calls core cache functions
3. Formats outputs for MCP
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from sensei.cli import run_server
from sensei.types import NoResults, Success

from .tools import get_cached_response as _get_cached_response
from .tools import search_cache as _search_cache

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

mcp = FastMCP(name="kura", lifespan=lifespan)


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool
async def search(
    query: Annotated[str, Field(description="Keywords to search for in cached queries")],
    limit: Annotated[int, Field(description="Maximum number of results", ge=1, le=50)] = 10,
) -> str:
    """Search the knowledge cache for previously researched topics.

    The cache stores past research as reusable building blocks. When answering a
    complex question, decompose it into parts and search for each - e.g., "compare
    fumadocs vs docusaurus" becomes separate searches for each framework.

    Returns matching queries with IDs. Use the `get` tool to retrieve full responses.

    Examples:
        - query="react hooks" - find cached research about React hooks
        - query="fastapi authentication" - find auth patterns for FastAPI
    """
    match await _search_cache(query, limit=limit):
        case Success(result):
            return result
        case NoResults():
            return f"No cached queries matching '{query}'"


@mcp.tool
async def get(
    query_id: Annotated[str, Field(description="The ID of the cached query to retrieve")],
) -> str:
    """Retrieve a full cached response by its ID.

    Use this after finding relevant hits with the `search` tool. Returns the
    complete cached research including the original query, response, and metadata.

    Cached responses can be composed together to answer new questions without
    re-doing the same research.
    """
    # Convert str → UUID at the edge (MCP receives JSON strings)
    match await _get_cached_response(UUID(query_id)):
        case Success(result):
            return result
        case NoResults():
            return f"No cached query found with ID '{query_id}'"


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Entry point for `uv run kura` or `python -m sensei.kura`."""
    run_server(mcp, "kura", "Kura knowledge cache MCP server")
