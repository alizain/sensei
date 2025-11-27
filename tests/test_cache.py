"""Tests for cache operations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sensei.types import CacheHit, SubSenseiResult


def test_cache_hit_model():
	"""Test CacheHit domain model."""
	hit = CacheHit(
		query_id="q-123",
		query_truncated="How do React hooks...",
		age_days=5,
		library="react",
		version="18.0",
	)
	assert hit.query_id == "q-123"
	assert hit.age_days == 5


def test_sub_sensei_result_model():
	"""Test SubSenseiResult domain model."""
	# From cache
	result_cached = SubSenseiResult(
		query_id="q-456",
		response_markdown="# Answer\n\n...",
		from_cache=True,
		age_days=10,
	)
	assert result_cached.from_cache is True
	assert result_cached.age_days == 10

	# Fresh result
	result_fresh = SubSenseiResult(
		query_id="q-789",
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
	mock_hits = [
		CacheHit(query_id="q1", query_truncated="React hooks...", age_days=5, library="react", version="18"),
		CacheHit(query_id="q2", query_truncated="React state...", age_days=10, library="react", version=None),
	]

	with patch("sensei.tools.cache.storage.search_queries_fts", new_callable=AsyncMock) as mock_search:
		mock_search.return_value = mock_hits

		from sensei.tools.cache import search_cache

		result = await search_cache("React hooks", library="react", limit=5)

		mock_search.assert_called_once_with("React hooks", library="react", version=None, limit=5)
		from sensei.types import Success

		assert isinstance(result, Success)
		assert "q1" in result.data
		assert "5 days" in result.data
		assert "q2" in result.data


@pytest.mark.asyncio
async def test_search_cache_no_results():
	"""Test search_cache returns NoResults when empty."""
	with patch("sensei.tools.cache.storage.search_queries_fts", new_callable=AsyncMock) as mock_search:
		mock_search.return_value = []

		from sensei.tools.cache import search_cache

		result = await search_cache("nonexistent")

		from sensei.types import NoResults

		assert isinstance(result, NoResults)


@pytest.mark.asyncio
async def test_get_cached_response_tool():
	"""Test get_cached_response returns full cached data."""
	from datetime import UTC, datetime

	mock_query = MagicMock()
	mock_query.query_id = "q1"
	mock_query.query = "How do React hooks work?"
	mock_query.output = "# React Hooks\n\nHooks are..."
	mock_query.sources_used = '["context7", "tavily"]'
	mock_query.created_at = datetime.now(UTC)

	with patch("sensei.tools.cache.storage.get_query", new_callable=AsyncMock) as mock_get:
		mock_get.return_value = mock_query

		from sensei.tools.cache import get_cached_response

		result = await get_cached_response("q1")

		mock_get.assert_called_once_with("q1")
		from sensei.types import Success

		assert isinstance(result, Success)
		assert "React Hooks" in result.data
		assert "context7" in result.data


@pytest.mark.asyncio
async def test_get_cached_response_not_found():
	"""Test get_cached_response returns NoResults when not found."""
	with patch("sensei.tools.cache.storage.get_query", new_callable=AsyncMock) as mock_get:
		mock_get.return_value = None

		from sensei.tools.cache import get_cached_response

		result = await get_cached_response("nonexistent")

		from sensei.types import NoResults

		assert isinstance(result, NoResults)


def test_deps_has_cache_fields():
	"""Test Deps has fields for sub-sensei context."""
	from sensei.deps import Deps

	deps = Deps(
		query_id="q1",
		parent_query_id="parent-q",
		current_depth=1,
		max_depth=2,
	)
	assert deps.parent_query_id == "parent-q"
	assert deps.current_depth == 1
	assert deps.max_depth == 2


def test_deps_cache_fields_default():
	"""Test Deps cache fields have sensible defaults."""
	from sensei.deps import Deps

	deps = Deps(query_id="q1")
	assert deps.parent_query_id is None
	assert deps.current_depth == 0
	assert deps.max_depth == 2


def test_create_sub_agent_exists():
	"""Test create_sub_agent factory function exists."""
	from sensei.tools.sub_agent import create_sub_agent

	# Just verify the function exists and is callable
	assert callable(create_sub_agent)


@pytest.mark.asyncio
async def test_spawn_sub_agent_tool_exists():
	"""Test spawn_sub_agent tool exists and has correct signature."""
	from sensei.tools.sub_agent import spawn_sub_agent
	import inspect

	sig = inspect.signature(spawn_sub_agent)
	params = list(sig.parameters.keys())
	assert "ctx" in params
	assert "sub_question" in params


@pytest.mark.asyncio
async def test_spawn_sub_agent_checks_depth():
	"""Test spawn_sub_agent respects max depth."""
	from sensei.tools.sub_agent import spawn_sub_agent
	from sensei.deps import Deps
	from pydantic_ai import RunContext

	# Create mock context at max depth
	mock_ctx = MagicMock(spec=RunContext)
	mock_ctx.deps = Deps(query_id="q1", current_depth=2, max_depth=2)

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
	"""Test CACHE_TOOLS includes cache usage instructions."""
	from sensei.prompts import CACHE_TOOLS

	assert "search_cache" in CACHE_TOOLS
	assert "spawn_sub_agent" in CACHE_TOOLS
	assert "decompos" in CACHE_TOOLS.lower()  # decompose/decomposition


@pytest.mark.asyncio
async def test_prefetch_cache_instruction():
	"""Test pre-fetch cache instruction function exists."""
	from sensei.agent import prefetch_cache_hits
	import inspect

	assert inspect.iscoroutinefunction(prefetch_cache_hits)
