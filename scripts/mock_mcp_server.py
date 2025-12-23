"""Mock MCP server with a slow tool to trigger timeout bugs."""

import asyncio

from fastmcp import FastMCP

mcp = FastMCP("docs-server")


@mcp.tool()
async def search_documentation(query: str) -> str:
    """Search programming documentation for any library, framework, or language.

    Use this tool to find documentation, API references, code examples,
    and tutorials for any programming topic.
    """
    await asyncio.sleep(60)
    return f"Documentation for: {query}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000)
