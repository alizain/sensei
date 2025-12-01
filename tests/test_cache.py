"""Tests for cache operations."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from sensei.types import CacheHit, SubSenseiResult


def test_cache_hit_model():
    """Test CacheHit domain model."""
    test_uuid = UUID("12345678-1234-5678-1234-567812345678")
    hit = CacheHit(
        query_id=test_uuid,
        query_truncated="How do React hooks...",
        age_days=5,
        library="react",
        version="18.0",
    )
    assert hit.query_id == test_uuid
    assert hit.age_days == 5


def test_sub_sensei_result_model():
    """Test SubSenseiResult domain model."""
    uuid1 = UUID("12345678-1234-5678-1234-567812345678")
    uuid2 = UUID("87654321-4321-8765-4321-876543218765")

    # From cache
    result_cached = SubSenseiResult(
        query_id=uuid1,
        response_markdown="# Answer\n\n...",
        from_cache=True,
        age_days=10,
    )
    assert result_cached.from_cache is True
    assert result_cached.age_days == 10

    # Fresh result
    result_fresh = SubSenseiResult(
        query_id=uuid2,
        response_markdown="# Fresh Answer\n\n...",
        from_cache=False,
        age_days=None,
    )
    assert result_fresh.from_cache is False
    assert result_fresh.age_days is None


def test_cache_config_defaults():
    """Test cache config has correct defaults."""
    from sensei.config import Settings

    s = Settings()
    assert s.cache_ttl_days == 30
    assert s.max_recursion_depth == 2


@pytest.mark.asyncio
async def test_search_cache_tool():
    """Test search_cache tool returns formatted results."""
    uuid1 = UUID("11111111-1111-1111-1111-111111111111")
    uuid2 = UUID("22222222-2222-2222-2222-222222222222")
    mock_hits = [
        CacheHit(query_id=uuid1, query_truncated="React hooks...", age_days=5, library="react", version="18"),
        CacheHit(query_id=uuid2, query_truncated="React state...", age_days=10, library="react", version=None),
    ]

    with patch("sensei.kura.tools.storage.search_queries", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_hits

        from sensei.kura.tools import search_cache

        result = await search_cache("React hooks", limit=5)

        # search_cache passes the query string directly to storage
        mock_search.assert_called_once_with("React hooks", limit=5)
        from sensei.types import Success

        assert isinstance(result, Success)
        assert str(uuid1) in result.data
        assert "5 days" in result.data
        assert str(uuid2) in result.data


@pytest.mark.asyncio
async def test_search_cache_no_results():
    """Test search_cache returns NoResults when empty."""
    with patch("sensei.kura.tools.storage.search_queries", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []

        from sensei.kura.tools import search_cache

        result = await search_cache("nonexistent")

        from sensei.types import NoResults

        assert isinstance(result, NoResults)


@pytest.mark.asyncio
async def test_get_cached_response_tool():
    """Test get_cached_response returns full cached data."""
    test_uuid = UUID("12345678-1234-5678-1234-567812345678")
    mock_query = MagicMock()
    mock_query.id = test_uuid
    mock_query.query = "How do React hooks work?"
    mock_query.output = "# React Hooks\n\nHooks are..."
    mock_query.inserted_at = datetime.now(UTC)

    with patch("sensei.kura.tools.storage.get_query", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_query

        from sensei.kura.tools import get_cached_response

        result = await get_cached_response(test_uuid)

        mock_get.assert_called_once_with(test_uuid)
        from sensei.types import Success

        assert isinstance(result, Success)
        assert "React Hooks" in result.data


@pytest.mark.asyncio
async def test_get_cached_response_not_found():
    """Test get_cached_response returns NoResults when not found."""
    fake_uuid = UUID("00000000-0000-0000-0000-000000000000")
    with patch("sensei.kura.tools.storage.get_query", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        from sensei.kura.tools import get_cached_response

        result = await get_cached_response(fake_uuid)

        from sensei.types import NoResults

        assert isinstance(result, NoResults)


def test_deps_has_cache_fields():
    """Test Deps has fields for sub-sensei context."""
    from sensei.deps import Deps

    query_uuid = UUID("11111111-1111-1111-1111-111111111111")
    parent_uuid = UUID("22222222-2222-2222-2222-222222222222")
    deps = Deps(
        query_id=query_uuid,
        parent_id=parent_uuid,
        current_depth=1,
        max_depth=2,
    )
    assert deps.parent_id == parent_uuid
    assert deps.current_depth == 1
    assert deps.max_depth == 2


def test_deps_cache_fields_default():
    """Test Deps cache fields have sensible defaults."""
    from sensei.deps import Deps

    query_uuid = UUID("11111111-1111-1111-1111-111111111111")
    deps = Deps(query_id=query_uuid)
    assert deps.parent_id is None
    assert deps.current_depth == 0
    assert deps.max_depth == 2


def test_create_sub_agent_exists():
    """Test create_sub_agent factory function exists."""
    from sensei.agent import create_sub_agent

    # Just verify the function exists and is callable
    assert callable(create_sub_agent)


@pytest.mark.asyncio
async def test_spawn_sub_agent_tool_exists():
    """Test spawn_sub_agent tool exists and has correct signature."""
    import inspect

    from sensei.agent import spawn_sub_agent

    sig = inspect.signature(spawn_sub_agent)
    params = list(sig.parameters.keys())
    assert "ctx" in params
    assert "sub_question" in params


@pytest.mark.asyncio
async def test_spawn_sub_agent_checks_depth():
    """Test spawn_sub_agent respects max depth."""
    from pydantic_ai import RunContext

    from sensei.agent import spawn_sub_agent
    from sensei.deps import Deps

    # Create mock context at max depth
    query_uuid = UUID("11111111-1111-1111-1111-111111111111")
    mock_ctx = MagicMock(spec=RunContext)
    mock_ctx.deps = Deps(query_id=query_uuid, current_depth=2, max_depth=2)

    result = await spawn_sub_agent(mock_ctx, "What is X?")

    # Should return error string about max depth
    assert "max depth" in result.lower()


def test_main_agent_has_exec_plan_tools():
    """Test main agent has exec plan tools registered."""
    from sensei.agent import agent

    tool_names = list(agent._function_toolset.tools)
    assert "add_exec_plan" in tool_names
    assert "update_exec_plan" in tool_names


def test_cache_prompt_includes_cache_instructions():
    """Test QUERY_DECOMPOSITION includes cache and subagent usage instructions."""
    from sensei.prompts import QUERY_DECOMPOSITION

    assert "cache" in QUERY_DECOMPOSITION.lower()
    assert "subagent" in QUERY_DECOMPOSITION.lower()
    assert "decompos" in QUERY_DECOMPOSITION.lower()  # decompose/decomposition


@pytest.mark.asyncio
async def test_prefetch_cache_instruction():
    """Test pre-fetch cache instruction function exists."""
    import inspect

    from sensei.agent import prefetch_cache_hits

    assert inspect.iscoroutinefunction(prefetch_cache_hits)
