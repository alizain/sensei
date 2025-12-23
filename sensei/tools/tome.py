"""Tome toolset for llms.txt documentation."""

from pydantic_ai.toolsets.fastmcp import FastMCPToolset

from sensei.tome.server import mcp as tome_mcp


def create_tome_server() -> FastMCPToolset:
    """Create Tome toolset.

    Returns:
        FastMCPToolset wrapping the Tome FastMCP server directly (no HTTP)

    Tome provides llms.txt documentation tools:
    - get: Retrieve a document by domain and path
    - search: Full-text search within ingested documents
    """
    return FastMCPToolset(tome_mcp).prefixed("tome")
