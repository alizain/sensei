"""Tome: Documentation repository from llms.txt sources.

Tome provides MCP tools to ingest and search llms.txt documentation:
- ingest: Crawl a domain's llms.txt and linked documents
- search: Full-text search across ingested documentation
- get: Retrieve a specific document by path

Usage as MCP server:
    from sensei.tome import mcp
    mcp.run()  # stdio transport
    # or
    app = mcp.http_app(path="/tome")  # HTTP transport

Usage as library:
    from sensei.tome import ingest_domain, tome_get, tome_search

    result = await ingest_domain("llmstext.org")
    docs = await tome_search("llmstext.org", "useState")
"""

from sensei.tome.crawler import ingest_domain
from sensei.tome.server import main, mcp
from sensei.tome.service import tome_get, tome_search

__all__ = [
    # Server
    "mcp",
    "main",
    # Service
    "ingest_domain",
    "tome_get",
    "tome_search",
]
