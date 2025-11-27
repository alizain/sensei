"""Tavily MCP server for AI-focused web search and extraction."""

from pydantic_ai.mcp import MCPServerStreamableHTTP


def create_tavily_server(api_key: str) -> MCPServerStreamableHTTP:
	"""Create Tavily MCP server connection.

	Args:
	    api_key: Tavily API key for authentication

	Returns:
	    MCPServerStreamableHTTP instance configured for Tavily

	Tavily provides AI-focused web search, extraction, and crawling capabilities.
	Tools available: search, extract, crawl, map
	"""
	return MCPServerStreamableHTTP(
		f"https://mcp.tavily.com/mcp/?tavilyApiKey={api_key}",
		tool_prefix="tavily",
	)
