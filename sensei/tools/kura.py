"""Kura toolset for query response cache."""

from pydantic_ai.toolsets.fastmcp import FastMCPToolset

from sensei.kura.server import mcp as kura_mcp


def create_kura_server() -> FastMCPToolset:
    """Create Kura toolset.

    Returns:
        FastMCPToolset wrapping the Kura FastMCP server directly (no HTTP)

    Kura provides query response cache tools:
    - search: Full-text search across cached queries
    - get: Retrieve a full cached response by ID
    """
    return FastMCPToolset(kura_mcp).prefixed("kura")
