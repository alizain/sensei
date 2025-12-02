"""Kura: Query response cache with full-text search.

Kura provides MCP tools to search and retrieve cached query responses:
- search: Full-text search across cached queries
- get: Retrieve a full cached response by ID

All tools connect to the same PostgreSQL database as the main Sensei app.

Usage as MCP server:
    from sensei.kura import kura
    kura.run()  # stdio transport
    # or
    app = kura.http_app(path="/kura")  # HTTP transport

Usage as library:
    from sensei.kura import search_cache, get_cached_response

    result = await search_cache("react hooks", library="react")
    response = await get_cached_response("query-123")
"""

from .server import kura, main
from .tools import get_cached_response, search_cache

__all__ = [
    # Server
    "kura",
    "main",
    # Tools
    "search_cache",
    "get_cached_response",
]
