"""Database engine and session factory configuration.

Engine is created at module import, requiring SENSEI_DATABASE_URL to be set.
If missing, Pydantic raises SettingsError during import (fail-fast).
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sensei.settings import sensei_settings

engine = create_async_engine(
    sensei_settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

_test_session_factory: async_sessionmaker | None = None


def get_session_factory() -> async_sessionmaker:
    """Get session factory, preferring test override if set."""
    return _test_session_factory or async_session_factory


def set_test_session_factory(factory: async_sessionmaker | None) -> None:
    """Set test session factory override (for transaction rollback pattern)."""
    global _test_session_factory
    _test_session_factory = factory


async def dispose_engine() -> None:
    """Dispose the engine to release database connections."""
    await engine.dispose()
