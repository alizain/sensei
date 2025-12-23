"""Unified MCP server for Sensei.

Mounts all sub-servers into a single MCP endpoint:
- query, feedback (core)
- scout_glob, scout_read, scout_grep, scout_tree
- kura_search, kura_get
- tome_get, tome_search

Usage:
    from sensei import mcp
    mcp.run()  # stdio transport
    # or
    app = mcp.http_app(path="/")  # HTTP transport (use path="/" when mounting)
"""

from contextlib import asynccontextmanager

from fastmcp import FastMCP

from sensei.database.engine import dispose_engine
from sensei.kura import mcp as kura_mcp
from sensei.scout import mcp as scout_mcp
from sensei.server import mcp as sensei_mcp
from sensei.tome import mcp as tome_mcp


@asynccontextmanager
async def lifespan(server):
    """Dispose database connections when the server shuts down."""
    try:
        yield
    finally:
        await dispose_engine()


# Create unified MCP server
mcp = FastMCP(name="sensei", lifespan=lifespan)

# Mount all sub-servers with prefixes
mcp.mount(sensei_mcp)
mcp.mount(scout_mcp, prefix="scout")
mcp.mount(kura_mcp, prefix="kura")
mcp.mount(tome_mcp, prefix="tome")
