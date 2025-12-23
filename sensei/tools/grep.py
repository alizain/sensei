"""Grep.app MCP server for code search across public repositories."""

from pydantic_ai.mcp import MCPServerStreamableHTTP


def create_grep_server() -> MCPServerStreamableHTTP:
    """Create Grep.app MCP server connection.

    Returns:
        MCPServerStreamableHTTP instance configured for Grep.app

    Grep.app provides code search across millions of public repositories.
    Useful for finding real-world usage examples and patterns.
    """
    return MCPServerStreamableHTTP(
        "https://mcp.grep.app",
        tool_prefix="grep",
    )
