"""FastMCP server for Kura cache tools.

This is the edge layer that:
1. Validates and parses MCP tool inputs
2. Calls core cache functions
3. Formats outputs for MCP
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from sensei.types import NoResults, Success

from .tools import get_cached_response as _get_cached_response
from .tools import search_cache as _search_cache

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# FastMCP Server
# ─────────────────────────────────────────────────────────────────────────────

kura = FastMCP(name="kura")


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


@kura.tool
async def search(
	query: Annotated[str, Field(description="Keywords to search for in cached queries")],
	limit: Annotated[int, Field(description="Maximum number of results", ge=1, le=50)] = 10,
) -> str:
	"""Search cached queries for relevant past answers.

	Use this to find previously answered documentation questions that might help.
	Returns a list of matching queries with IDs, which you can retrieve in full
	using the get tool.

	Examples:
	    - query="react hooks" - find cached answers about React hooks
	    - query="async patterns", limit=5 - top 5 async pattern answers
	"""
	match await _search_cache(query, limit=limit):
		case Success(result):
			return result
		case NoResults():
			return f"No cached queries matching '{query}'"


@kura.tool
async def get(
	query_id: Annotated[str, Field(description="The ID of the cached query to retrieve")],
) -> str:
	"""Retrieve a full cached response by query ID.

	Use this after finding relevant cache hits with the search tool.
	Returns the complete original query and cached response with metadata.

	Example:
	    - query_id="abc123" - get the full cached response for query abc123
	"""
	# Convert str → UUID at the edge (MCP receives JSON strings)
	match await _get_cached_response(UUID(query_id)):
		case Success(result):
			return result
		case NoResults():
			return f"No cached query found with ID '{query_id}'"
