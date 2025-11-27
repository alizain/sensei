"""Tests for database operations."""

import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sensei.database import storage
from sensei.database.models import Base
from sensei.types import Rating


@pytest_asyncio.fixture
async def test_db():
	"""Create a temporary test database."""
	# Create a temporary file for the test database
	fd, db_path = tempfile.mkstemp(suffix=".db")
	os.close(fd)

	# Override the engine with a test database
	test_engine = create_async_engine(
		f"sqlite+aiosqlite:///{db_path}",
		echo=False,
	)

	# Override the global engine and session factory
	original_engine = storage.engine
	original_session = storage.AsyncSessionLocal

	storage.engine = test_engine
	storage.AsyncSessionLocal = async_sessionmaker(
		test_engine,
		class_=AsyncSession,
		expire_on_commit=False,
	)

	# Create tables
	async with test_engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)

	yield test_engine

	# Cleanup
	await test_engine.dispose()
	storage.engine = original_engine
	storage.AsyncSessionLocal = original_session
	os.unlink(db_path)


@pytest.mark.asyncio
async def test_init_db(test_db):
	"""Test database initialization."""
	# init_db should be idempotent
	await storage.init_db()
	await storage.init_db()  # Should not fail


@pytest.mark.asyncio
async def test_save_query(test_db):
	"""Test saving a query."""
	query_id = "test-query-123"
	query = "How do I use FastAPI?"
	markdown = "# FastAPI Usage\n\nHere's how..."
	sources = ["context7", "scout"]

	await storage.save_query(query_id, query, output=markdown, sources_used=sources)

	# Retrieve and verify
	retrieved = await storage.get_query(query_id)
	assert retrieved is not None
	assert retrieved.query_id == query_id
	assert retrieved.query == query
	assert retrieved.output == markdown
	assert retrieved.sources_used == '["context7", "scout"]'


@pytest.mark.asyncio
async def test_save_query_without_sources(test_db):
	"""Test saving a query without sources."""
	query_id = "test-query-456"
	query = "What is Python?"
	markdown = "# Python\n\nPython is..."

	await storage.save_query(query_id, query, output=markdown)

	retrieved = await storage.get_query(query_id)
	assert retrieved is not None
	assert retrieved.sources_used is None


@pytest.mark.asyncio
async def test_save_rating(test_db):
	"""Test saving a rating."""
	# First create a query
	query_id = "test-query-789"
	await storage.save_query(query_id, "test query", output="test response")

	# Save a rating with all fields
	rating1 = Rating(
		query_id=query_id,
		correctness=5,
		relevance=4,
		usefulness=5,
		reasoning="Great response!",
		agent_model="model-x",
		agent_system="agent-y",
		agent_version="1.0",
	)
	await storage.save_rating(rating1)

	# Save another rating without optional fields
	rating2 = Rating(
		query_id=query_id,
		correctness=3,
		relevance=3,
		usefulness=2,
	)
	await storage.save_rating(rating2)


@pytest.mark.asyncio
async def test_get_query_not_found(test_db):
	"""Test retrieving a non-existent query."""
	retrieved = await storage.get_query("non-existent-query")
	assert retrieved is None


@pytest.mark.asyncio
async def test_save_query_with_parent_and_depth(test_db):
	"""Test saving a sub-query with parent reference and depth."""
	# Create parent query
	parent_id = "parent-query-001"
	await storage.save_query(parent_id, "Main question?", output="Main answer")

	# Create child query
	child_id = "child-query-001"
	await storage.save_query(
		query_id=child_id,
		query="Sub question?",
		output="Sub answer",
		parent_query_id=parent_id,
		depth=1,
	)

	# Verify child has correct parent and depth
	child = await storage.get_query(child_id)
	assert child is not None
	assert child.parent_query_id == parent_id
	assert child.depth == 1

	# Verify parent has no parent and depth 0
	parent = await storage.get_query(parent_id)
	assert parent is not None
	assert parent.parent_query_id is None
	assert parent.depth == 0


@pytest.mark.asyncio
async def test_fts5_table_created(test_db):
	"""Test FTS5 virtual table is created during init."""
	from sqlalchemy import text

	# Run init_db to create FTS5 table
	await storage.init_db()

	async with storage.AsyncSessionLocal() as session:
		# Check if queries_fts table exists
		result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='queries_fts'"))
		row = result.scalar_one_or_none()
		assert row == "queries_fts", "FTS5 table should exist"


@pytest.mark.asyncio
async def test_fts5_syncs_on_insert(test_db):
	"""Test FTS5 table syncs when queries are inserted."""
	from sqlalchemy import text

	# Run init_db to create FTS5 table and triggers
	await storage.init_db()

	# Save a query
	await storage.save_query("fts-test-001", "How do React hooks work?", output="Answer here")

	# Search via FTS5
	async with storage.AsyncSessionLocal() as session:
		result = await session.execute(
			text(
				"SELECT query_id FROM queries WHERE rowid IN (SELECT rowid FROM queries_fts WHERE queries_fts MATCH 'React hooks')"
			)
		)
		rows = result.fetchall()
		assert len(rows) == 1
		assert rows[0][0] == "fts-test-001"


@pytest.mark.asyncio
async def test_search_queries_fts(test_db):
	"""Test FTS5 search function."""
	# Initialize with FTS5
	await storage.init_db()

	# Insert test data
	await storage.save_query("q1", "How do React hooks work?", output="Answer 1", library="react", version="18")
	await storage.save_query("q2", "React component lifecycle", output="Answer 2", library="react")
	await storage.save_query("q3", "Python async await", output="Answer 3", library="python")

	# Search for "React"
	results = await storage.search_queries_fts("React", limit=10)
	assert len(results) == 2
	query_ids = [r.query_id for r in results]
	assert "q1" in query_ids
	assert "q2" in query_ids

	# Search with library filter
	results = await storage.search_queries_fts("lifecycle", library="react", limit=10)
	assert len(results) == 1
	assert results[0].query_id == "q2"

	# Search that matches nothing
	results = await storage.search_queries_fts("nonexistent", limit=10)
	assert len(results) == 0
