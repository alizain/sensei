"""Integration tests for cache functionality."""

import pytest

from sensei.database import storage
from sensei.kura.tools import get_cached_response, search_cache
from sensei.types import Success


@pytest.mark.asyncio
async def test_cache_search_and_retrieve_flow(integration_db):
    """Test full flow: save query, search cache, retrieve response."""
    # Save a query
    query_id = await storage.save_query(
        query="How do React hooks work in functional components?",
        output="# React Hooks\n\nHooks let you use state in functional components...",
        library="react",
        version="18",
    )

    # Search for it
    search_result = await search_cache("React hooks functional")
    assert isinstance(search_result, Success)
    assert str(query_id) in search_result.data  # search_cache returns formatted string

    # Retrieve full response (takes UUID directly)
    get_result = await get_cached_response(query_id)
    assert isinstance(get_result, Success)
    assert "React Hooks" in get_result.data
    assert "functional components" in get_result.data


@pytest.mark.asyncio
async def test_parent_child_query_relationship(integration_db):
    """Test sub-query parent relationship is preserved."""
    # Create parent
    parent_id = await storage.save_query(
        query="Why are my React hooks breaking?",
        output="# Analysis\n\nLet me break this down...",
    )

    # Create child
    child_id = await storage.save_query(
        query="How do React hooks work?",
        output="# React Hooks Basics\n\n...",
        parent_id=parent_id,
    )

    # Verify relationship
    child = await storage.get_query(child_id)
    assert child is not None
    assert child.parent_id == parent_id
