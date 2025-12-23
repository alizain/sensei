"""CLI entry point for unified Sensei MCP server.

Usage:
    python -m sensei              # stdio (default)
    python -m sensei -t http      # HTTP on port 8000
    python -m sensei -t sse -p 9000
"""

import logging

from fastmcp.utilities.logging import configure_logging

from sensei.cli import run_server
from sensei.unified import mcp

# Configure logging when run as CLI
configure_logging(level="DEBUG")  # fastmcp logger
configure_logging(level="DEBUG", logger=logging.getLogger("sensei"))  # sensei logger


def main():
    """Entry point for `python -m sensei`."""
    run_server(mcp, "sensei", "Unified Sensei MCP server")


if __name__ == "__main__":
    main()
