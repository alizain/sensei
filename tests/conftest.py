"""Shared test fixtures using PostgreSQL and Alembic migrations.

Prerequisites:
    1. PostgreSQL running (docker-compose up -d postgres)
    2. Test database created:
       psql -h localhost -U sensei -d sensei -c "CREATE DATABASE sensei_test"
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sensei.database import storage

# Test database URL - uses a separate test database
# Default assumes docker-compose postgres with sensei_test database
TEST_DATABASE_URL = "postgresql+asyncpg://sensei:sensei@localhost:5432/sensei_test"


def _run_migrations_sync(database_url: str) -> None:
	"""Run Alembic migrations against the given database URL (sync helper)."""
	config = Config("alembic.ini")
	config.set_main_option("sqlalchemy.url", database_url)
	command.upgrade(config, "head")


async def run_migrations(database_url: str) -> None:
	"""Run Alembic migrations in a thread (async-safe)."""
	loop = asyncio.get_event_loop()
	with ThreadPoolExecutor() as pool:
		await loop.run_in_executor(pool, _run_migrations_sync, database_url)


@pytest_asyncio.fixture
async def test_db():
	"""Create a test database with migrations applied.

	This fixture:
	1. Runs all Alembic migrations
	2. Overrides storage module to use test database
	3. Cleans up tables after test (keeps schema)

	Prerequisites:
	    - PostgreSQL running on localhost:5432
	    - Database 'sensei_test' must exist
	    - User 'sensei' with password 'sensei' must have access
	"""
	# Run migrations in a thread to avoid event loop conflict
	await run_migrations(TEST_DATABASE_URL)

	# Create test engine
	test_engine = create_async_engine(
		TEST_DATABASE_URL,
		echo=False,
	)

	# Override storage module's engine and session factory
	original_engine = storage._engine
	original_session_factory = storage._async_session_local

	storage._engine = test_engine
	storage._async_session_local = async_sessionmaker(
		test_engine,
		class_=AsyncSession,
		expire_on_commit=False,
	)

	yield test_engine

	# Clean up data (truncate tables, keep schema)
	async with test_engine.begin() as conn:
		await conn.execute(text("TRUNCATE TABLE sections, ratings, documents, queries CASCADE"))

	# Restore original engine
	await test_engine.dispose()
	storage._engine = original_engine
	storage._async_session_local = original_session_factory


@pytest_asyncio.fixture
async def integration_db(test_db):
	"""Alias for test_db for backwards compatibility with integration tests."""
	yield test_db
