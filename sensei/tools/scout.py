"""Scout toolset for GitHub repository exploration."""

from pydantic_ai.toolsets.fastmcp import FastMCPToolset

from sensei.scout.server import mcp as scout_mcp


def create_scout_server() -> FastMCPToolset:
    """Create Scout toolset.

    Returns:
        FastMCPToolset wrapping the Scout FastMCP server directly (no HTTP)

    Scout provides GitHub repository exploration tools:
    - glob: Find files by pattern
    - read: Read file contents
    - grep: Search patterns with context
    - tree: Directory structure
    """
    return FastMCPToolset(scout_mcp).prefixed("scout")
