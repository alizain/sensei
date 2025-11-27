"""Integration tests for cache functionality."""

import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sensei.database import storage


@pytest_asyncio.fixture
async def integration_db():
	"""Create a temporary test database for integration tests."""
	fd, db_path = tempfile.mkstemp(suffix=".db")
	os.close(fd)

	test_engine = create_async_engine(
		f"sqlite+aiosqlite:///{db_path}",
		echo=False,
	)

	original_engine = storage.engine
	original_session = storage.AsyncSessionLocal

	storage.engine = test_engine
	storage.AsyncSessionLocal = async_sessionmaker(
		test_engine,
		class_=AsyncSession,
		expire_on_commit=False,
	)

	# Initialize with FTS5
	await storage.init_db()

	yield test_engine

	await test_engine.dispose()
	storage.engine = original_engine
	storage.AsyncSessionLocal = original_session
	os.unlink(db_path)


@pytest.mark.asyncio
async def test_cache_search_and_retrieve_flow(integration_db):
	"""Test full flow: save query, search cache, retrieve response."""
	from sensei.tools.cache import search_cache, get_cached_response
	from sensei.types import Success

	# Save a query
	await storage.save_query(
		query_id="integration-q1",
		query="How do React hooks work in functional components?",
		output="# React Hooks\n\nHooks let you use state in functional components...",
		sources_used=["context7"],
		library="react",
		version="18",
	)

	# Search for it
	search_result = await search_cache("React hooks functional")
	assert isinstance(search_result, Success)
	assert "integration-q1" in search_result.data

	# Retrieve full response
	get_result = await get_cached_response("integration-q1")
	assert isinstance(get_result, Success)
	assert "React Hooks" in get_result.data
	assert "functional components" in get_result.data


@pytest.mark.asyncio
async def test_parent_child_query_relationship(integration_db):
	"""Test sub-query parent relationship is preserved."""
	# Create parent
	await storage.save_query(
		query_id="parent-001",
		query="Why are my React hooks breaking?",
		output="# Analysis\n\nLet me break this down...",
		depth=0,
	)

	# Create child
	await storage.save_query(
		query_id="child-001",
		query="How do React hooks work?",
		output="# React Hooks Basics\n\n...",
		parent_query_id="parent-001",
		depth=1,
	)

	# Verify relationship
	child = await storage.get_query("child-001")
	assert child is not None
	assert child.parent_query_id == "parent-001"
	assert child.depth == 1
