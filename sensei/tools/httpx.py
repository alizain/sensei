"""HTTP fetch tool for Sensei agent.

Provides a flexible httpx wrapper for fetching URLs during research.
Use this when Scout (GitHub), Tome (llms.txt), or Tavily (search) don't cover
the URL you need - like specific API endpoints, raw files, or documentation pages.
"""

import json
import logging
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field
from pydantic_ai.toolsets.fastmcp import FastMCPToolset

logger = logging.getLogger(__name__)

# Maximum response body size to return (avoid overwhelming context)
MAX_BODY_SIZE = 100_000  # 100KB

mcp = FastMCP(name="httpx")


@mcp.tool
async def fetch(
    url: Annotated[str, Field(description="The URL to fetch")],
    method: Annotated[
        str,
        Field(description="HTTP method: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS"),
    ] = "GET",
    headers: Annotated[
        dict[str, str] | None,
        Field(description="Custom HTTP headers"),
    ] = None,
    params: Annotated[
        dict[str, str] | None,
        Field(description="Query parameters to append to URL"),
    ] = None,
    json_body: Annotated[
        dict | list | None,
        Field(description="JSON body for POST/PUT/PATCH requests"),
    ] = None,
    data: Annotated[
        str | None,
        Field(description="Raw text body (alternative to json_body)"),
    ] = None,
    timeout: Annotated[
        float,
        Field(description="Request timeout in seconds", ge=1, le=120),
    ] = 30.0,
    follow_redirects: Annotated[
        bool,
        Field(description="Whether to follow HTTP redirects"),
    ] = True,
) -> str:
    """Fetch a URL and return the response.

    Use this for direct HTTP requests when other tools (Scout, Tome, Tavily)
    don't cover your needs. Supports all HTTP methods, custom headers, and
    request bodies.

    Examples:
        - fetch(url="https://api.github.com/repos/fastmcp/fastmcp")
        - fetch(url="https://example.com/api", method="POST", json_body={"key": "value"})
        - fetch(url="https://example.com/data", headers={"Authorization": "Bearer token"})
    """
    method = method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        return f"Invalid HTTP method: {method}"

    logger.info(f"Fetching {method} {url}")

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
        ) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_body,
                content=data,
            )
    except httpx.TimeoutException:
        return f"Request timed out after {timeout}s"
    except httpx.RequestError as e:
        return f"Request failed: {type(e).__name__}: {e}"

    return _format_response(response)


def _format_response(response: httpx.Response) -> str:
    """Format HTTP response for agent consumption."""
    lines = [
        f"## HTTP {response.status_code} {response.reason_phrase}",
        "",
        "### Headers",
    ]

    # Include useful headers
    useful_headers = [
        "content-type",
        "content-length",
        "location",
        "cache-control",
        "etag",
        "last-modified",
        "x-ratelimit-remaining",
        "retry-after",
    ]
    for header in useful_headers:
        if value := response.headers.get(header):
            lines.append(f"- **{header}:** {value}")

    lines.extend(["", "### Body", ""])

    # Handle body based on content type
    content_type = response.headers.get("content-type", "")
    body = response.text

    if len(body) > MAX_BODY_SIZE:
        body = body[:MAX_BODY_SIZE] + f"\n\n... (truncated, {len(response.text)} bytes total)"

    if "application/json" in content_type:
        try:
            parsed = response.json()
            body = json.dumps(parsed, indent=2)
            if len(body) > MAX_BODY_SIZE:
                body = body[:MAX_BODY_SIZE] + "\n\n... (truncated)"
            lines.append(f"```json\n{body}\n```")
        except json.JSONDecodeError:
            lines.append(f"```\n{body}\n```")
    elif "text/html" in content_type:
        lines.append(f"```html\n{body}\n```")
    elif "text/" in content_type or not body:
        lines.append(f"```\n{body}\n```")
    else:
        # Binary content - just note it
        lines.append(f"(Binary content, {len(response.content)} bytes)")

    return "\n".join(lines)


def create_httpx_server() -> FastMCPToolset:
    """Create httpx toolset for the Sensei agent.

    Returns:
        FastMCPToolset wrapping the httpx FastMCP server

    Provides:
        - fetch: Flexible HTTP requests with full control over method, headers, body
    """
    return FastMCPToolset(mcp)
