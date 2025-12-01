"""Tome MCP client for llms.txt documentation."""

from pydantic_ai.mcp import MCPServerStreamableHTTP

from sensei.config import settings


def create_tome_server(base_url: str = "http://localhost:8000") -> MCPServerStreamableHTTP:
	"""Create Tome MCP server connection.

	Args:
	    base_url: Base URL where Sensei is running. If None, uses settings.sensei_host.

	Returns:
	    MCPServerStreamableHTTP instance configured for Tome

	Tome provides llms.txt documentation tools:
	- ingest: Ingest a domain's llms.txt and linked docs
	- get: Retrieve a document by domain and path
	- search: Full-text search within ingested documents
	"""
	url = base_url or settings.sensei_host
	return MCPServerStreamableHTTP(
		f"{url}/tome/mcp",
		tool_prefix="tome",
	)
