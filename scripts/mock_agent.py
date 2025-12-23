"""Minimal PoC to reproduce pydantic_ai MCP cancel scope bug.

Run mock_mcp_server.py first, then run this script.
Expected: Timeout followed by RuntimeError about cancel scope.
"""

import asyncio

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from sensei.settings import general_settings


async def main():
    # Connect to our mock MCP server
    mcp_server = MCPServerStreamableHTTP(
        "http://127.0.0.1:8000/mcp",
        tool_prefix="docs",
    )

    model = GoogleModel(
        "gemini-2.5-flash-lite",
        provider=GoogleProvider(api_key=general_settings.google_api_key),
    )

    agent = Agent(
        model,
        toolsets=[mcp_server],
        system_prompt="You must always use the search_documentation tool to answer questions. Never answer without calling search_documentation first.",
    )

    print("=== Starting agent (expect timeout + cancel scope error) ===")
    async with agent:
        result = await agent.run("use search_documentation and return results regarding fastapi")
        print(f"Result: {result.output}")


if __name__ == "__main__":
    asyncio.run(main())
