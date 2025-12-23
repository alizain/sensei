"""Shared test fixtures using PostgreSQL and Alembic migrations.

Prerequisites:
    1. PostgreSQL running (docker-compose up -d postgres)
    2. Test database created:
       psql -h localhost -U sensei -d sensei -c "CREATE DATABASE sensei_test"
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Test database URL - uses a separate test database
# Default assumes docker-compose postgres with sensei_test database
TEST_DATABASE_URL = "postgresql+asyncpg://sensei:sensei@localhost:5432/sensei_test"
os.environ["SENSEI_DATABASE_URL"] = TEST_DATABASE_URL

from sensei.database.engine import engine, set_test_session_factory  # noqa: E402


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


class TestAsyncSession(AsyncSession):
    async def __aenter__(self) -> "TestAsyncSession":
        await super().__aenter__()
        await self.begin_nested()

        @event.listens_for(self.sync_session, "after_transaction_end")
        def _restart_savepoint(session, transaction):
            if transaction.nested and not transaction._parent.nested:
                session.begin_nested()

        return self


@pytest_asyncio.fixture(scope="session")
async def _run_migrations():
    """Apply all migrations once per test session."""
    await run_migrations(TEST_DATABASE_URL)


@pytest_asyncio.fixture
async def test_db(_run_migrations):
    """Provide a database with transaction rollback isolation.

    This fixture:
    1. Ensures all Alembic migrations are applied (session-scoped)
    2. Binds sessions to a connection with an outer transaction
    3. Rolls back the outer transaction after each test

    Prerequisites:
        - PostgreSQL running on localhost:5432
        - Database 'sensei_test' must exist
        - User 'sensei' with password 'sensei' must have access
    """
    async with engine.connect() as conn:
        trans = await conn.begin()
        test_session_factory = async_sessionmaker(
            bind=conn,
            class_=TestAsyncSession,
            expire_on_commit=False,
        )
        set_test_session_factory(test_session_factory)

        try:
            yield engine
        finally:
            set_test_session_factory(None)
            await trans.rollback()
