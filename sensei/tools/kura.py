"""Kura MCP client for query response cache."""

from pydantic_ai.mcp import MCPServerStreamableHTTP

from sensei.config import settings


def create_kura_server(base_url: str = "http://localhost:8000") -> MCPServerStreamableHTTP:
	"""Create Kura MCP server connection.

	Args:
	    base_url: Base URL where Sensei is running. If None, uses settings.sensei_host.

	Returns:
	    MCPServerStreamableHTTP instance configured for Kura

	Kura provides query response cache tools:
	- search: Full-text search across cached queries
	- get: Retrieve a full cached response by ID
	"""
	url = base_url or settings.sensei_host
	return MCPServerStreamableHTTP(
		f"{url}/kura/mcp",
		tool_prefix="kura",
	)
