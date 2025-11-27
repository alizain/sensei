"""Context7 MCP server for pre-indexed library documentation."""

from pydantic_ai.mcp import MCPServerStreamableHTTP


def create_context7_server(api_key: str) -> MCPServerStreamableHTTP:
	"""Create Context7 MCP server connection.

	Args:
	    api_key: Context7 API key for authentication

	Returns:
	    MCPServerStreamableHTTP instance configured for Context7

	Context7 provides pre-indexed library documentation from official sources.
	Tools available: resolve_library_id, get_library_docs
	"""
	return MCPServerStreamableHTTP(
		"https://mcp.context7.com/mcp",
		headers={"CONTEXT7_API_KEY": api_key},
		tool_prefix="context7",
	)
