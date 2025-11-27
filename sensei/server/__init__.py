"""Server implementations for Sensei (API and MCP)."""

# Note: Import app from sensei.main directly to avoid circular imports
# from sensei.main import app

from sensei.server.api import api_app
from sensei.server.mcp import mcp

__all__ = ["api_app", "mcp"]
