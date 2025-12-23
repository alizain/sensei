"""Tests for the REST API server."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from sensei.types import QueryResult


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    # Import after patches are set up
    from sensei.api import app

    return TestClient(app)


def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_query_endpoint_success(client):
    """Test successful query endpoint."""
    with patch("sensei.api.core.handle_query", new_callable=AsyncMock) as mock_handle:
        mock_handle.return_value = QueryResult(
            query_id="11111111-1111-1111-1111-111111111111",
            output="# FastAPI Guide\n\nHere's how to use FastAPI...\n\n---\n**Help improve sensei:** Rate this response using `feedback` tool after trying it.\n\nQuery ID: `11111111-1111-1111-1111-111111111111`\n",
        )

        response = client.post(
            "/query",
            json={"query": "How do I use FastAPI?"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "query_id" in data
        assert "output" in data

        # Verify query_id is a valid UUID
        try:
            uuid.UUID(data["query_id"])
        except ValueError:
            pytest.fail("query_id is not a valid UUID")

        # Verify output contains response and feedback template
        assert "FastAPI Guide" in data["output"]
        assert "Help improve sensei" in data["output"]


@pytest.mark.asyncio
async def test_query_endpoint_empty_query(client):
    """Test query endpoint with empty query."""
    response = client.post(
        "/query",
        json={"query": ""},
    )

    # Should fail validation due to min_length=1
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_endpoint_missing_query(client):
    """Test query endpoint with missing query field."""
    response = client.post(
        "/query",
        json={},
    )

    # Should fail validation due to required field
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_endpoint_agent_error(client):
    """Test query endpoint when agent raises an error."""
    from sensei.types import ToolError as SenseiToolError

    with patch("sensei.api.core.handle_query", new_callable=AsyncMock) as mock_handle:
        mock_handle.side_effect = SenseiToolError("Agent failed")

        response = client.post(
            "/query",
            json={"query": "test query"},
        )

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data


@pytest.mark.asyncio
async def test_rate_endpoint_success(client):
    """Test successful rating endpoint."""
    with patch("sensei.api.core.handle_rating", new_callable=AsyncMock) as mock_handle:
        response = client.post(
            "/rate",
            json={
                "query_id": "12345678-1234-5678-1234-567812345678",
                "correctness": 5,
                "relevance": 4,
                "usefulness": 5,
                "reasoning": "Worked in prod",
                "agent_model": "claude-3-5",
                "agent_system": "Claude Code",
                "agent_version": "2.0",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"

        # Verify mock was called
        mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_rate_endpoint_without_feedback(client):
    """Test rating endpoint without optional feedback."""
    with patch("sensei.api.core.handle_rating", new_callable=AsyncMock) as mock_handle:
        response = client.post(
            "/rate",
            json={
                "query_id": "22222222-2222-2222-2222-222222222222",
                "correctness": 3,
                "relevance": 3,
                "usefulness": 2,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "recorded"

        # Verify mock was called
        mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_rate_endpoint_invalid_rating(client):
    """Test rating endpoint with invalid rating value."""
    # Rating too low
    response = client.post(
        "/rate",
        json={
            "query_id": "test-query-789",
            "correctness": 0,
            "relevance": 3,
            "usefulness": 3,
        },
    )
    assert response.status_code == 422

    # Rating too high
    response = client.post(
        "/rate",
        json={
            "query_id": "test-query-789",
            "correctness": 6,
            "relevance": 3,
            "usefulness": 3,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rate_endpoint_missing_fields(client):
    """Test rating endpoint with missing required fields."""
    # Missing query_id
    response = client.post(
        "/rate",
        json={"correctness": 5, "relevance": 5, "usefulness": 5},
    )
    assert response.status_code == 422

    # Missing ratings
    response = client.post(
        "/rate",
        json={"query_id": "test-123"},
    )
    assert response.status_code == 422


def test_not_found_endpoint(client):
    """Test 404 handler for non-existent endpoints."""
    response = client.get("/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
