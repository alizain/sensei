"""Unified MCP server for Sensei.

Mounts all sub-servers into a single MCP endpoint:
- sensei_query, sensei_feedback (core)
- scout_glob, scout_read, scout_grep, scout_tree
- kura_search, kura_get
- tome_get, tome_search

Usage:
    python -m sensei              # stdio (default)
    python -m sensei -t http      # HTTP on port 8000
    python -m sensei -t sse -p 9000
"""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.utilities.logging import configure_logging

from sensei.cli import run_server
from sensei.kura import mcp as kura_mcp
from sensei.scout import mcp as scout_mcp
from sensei.server import mcp as sensei_mcp
from sensei.tome import mcp as tome_mcp

# Configure logging
configure_logging(level="DEBUG")  # fastmcp logger
configure_logging(level="DEBUG", logger=logging.getLogger("sensei"))  # sensei logger


@asynccontextmanager
async def lifespan(server):
    """Ensure database is ready before handling MCP requests."""
    from sensei.database.local import ensure_db_ready

    await ensure_db_ready()
    yield


# Create unified MCP server
mcp = FastMCP(name="sensei", lifespan=lifespan)

# Mount all sub-servers with prefixes
mcp.mount(sensei_mcp, prefix="sensei")
mcp.mount(scout_mcp, prefix="scout")
mcp.mount(kura_mcp, prefix="kura")
mcp.mount(tome_mcp, prefix="tome")


def main():
    """Entry point for `python -m sensei`."""
    run_server(mcp, "sensei", "Unified Sensei MCP server")


if __name__ == "__main__":
    main()
