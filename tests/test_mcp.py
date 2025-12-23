"""Tests for the core MCP server."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio
from fastmcp.client import Client
from fastmcp.exceptions import ToolError

from sensei.server import mcp as sensei_mcp
from sensei.types import QueryResult


@pytest_asyncio.fixture
async def mcp_client():
    async with Client(transport=sensei_mcp) as client:
        yield client


@pytest.mark.asyncio
async def test_list_tools(mcp_client: Client):
    """Test that list_tools returns the correct tools."""
    tools = await mcp_client.list_tools()

    assert len(tools) == 2
    tool_names = {t.name for t in tools}
    assert tool_names == {"query", "feedback"}


@pytest.mark.asyncio
async def test_query_tool_success(mcp_client: Client, monkeypatch):
    """Test successful query tool call."""
    test_uuid = UUID("12345678-1234-5678-1234-567812345678")
    monkeypatch.setattr(
        "sensei.core.handle_query",
        AsyncMock(
            return_value=QueryResult(query_id=test_uuid, output="# Test Response\n\nHere's the documentation...")
        ),
    )

    result = await mcp_client.call_tool("query", {"query": "How do I use FastAPI?"})

    assert result.data is not None
    assert "Test Response" in result.data


@pytest.mark.asyncio
async def test_query_tool_error(mcp_client: Client, monkeypatch, caplog):
    """Test query tool call with error."""
    import logging

    from sensei.types import TransientError

    monkeypatch.setattr("sensei.core.handle_query", AsyncMock(side_effect=TransientError("Agent failed")))

    with caplog.at_level(logging.ERROR, logger="sensei.server"):
        with pytest.raises(ToolError, match="Service temporarily unavailable"):
            await mcp_client.call_tool("query", {"query": "test query"})
        assert "Service temporarily unavailable" in caplog.text


@pytest.mark.asyncio
async def test_feedback_tool_success(mcp_client: Client, monkeypatch):
    """Test successful feedback tool call."""
    mock_handle_rating = AsyncMock()
    monkeypatch.setattr("sensei.core.handle_rating", mock_handle_rating)

    result = await mcp_client.call_tool(
        "feedback",
        {
            "query_id": "12345678-1234-5678-1234-567812345678",
            "correctness": 5,
            "relevance": 4,
            "usefulness": 5,
            "reasoning": "Great!",
        },
    )

    assert "Thank you" in result.data
    mock_handle_rating.assert_called_once()


@pytest.mark.asyncio
async def test_feedback_tool_error(mcp_client: Client, monkeypatch, caplog):
    """Test feedback tool call with error."""
    import logging

    monkeypatch.setattr("sensei.core.handle_rating", AsyncMock(side_effect=Exception("Database error")))

    with caplog.at_level(logging.ERROR, logger="sensei.server"):
        with pytest.raises(ToolError, match="Failed to save rating"):
            await mcp_client.call_tool(
                "feedback",
                {"query_id": "12345678-1234-5678-1234-567812345678", "correctness": 3, "relevance": 3, "usefulness": 3},
            )
        assert "Failed to save rating" in caplog.text


def test_server_name():
    """Test that the MCP server has the correct name."""
    assert sensei_mcp.name == "sensei-core"
