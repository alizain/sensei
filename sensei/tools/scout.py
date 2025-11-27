"""Scout MCP client for GitHub repository exploration."""

from pydantic_ai.mcp import MCPServerStreamableHTTP

from sensei.config import settings


def create_scout_server(base_url: str | None = None) -> MCPServerStreamableHTTP:
	"""Create Scout MCP server connection.

	Args:
	    base_url: Base URL where Sensei is running. If None, uses settings.sensei_host.

	Returns:
	    MCPServerStreamableHTTP instance configured for Scout

	Scout provides GitHub repository exploration tools:
	- repo_map: Structural overview (classes, functions, signatures)
	- glob: Find files by pattern
	- read: Read file contents
	- grep: Search patterns with context
	- tree: Directory structure
	"""
	url = base_url or settings.sensei_host
	return MCPServerStreamableHTTP(
		f"{url}/scout/mcp",
		tool_prefix="scout",
	)
