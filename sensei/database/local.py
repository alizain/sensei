"""PostgreSQL lifecycle management for sensei-managed mode.

This module handles:
- PostgreSQL lifecycle (init/start/stop) for sensei-managed mode
- Migration running for local mode only (thin wrapper on alembic)

Mode matrix:
| DATABASE_URL env var | is_external_database | Starts PG? | Migrates? |
|---------------------|---------------------|------------|-----------|
| Not set | False | Yes | Yes |
| Set | True | No | No |
"""

import logging
import shutil
import subprocess

from sensei.paths import get_pgdata, get_pg_log, get_sensei_home
from sensei.types import BrokenInvariant

logger = logging.getLogger(__name__)

# Idempotency flag - ensure_db_ready() may be called multiple times
# (e.g., from combined_lifespan AND individual service lifespans)
_db_ready = False


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL Lifecycle (sensei-managed mode only)
# ─────────────────────────────────────────────────────────────────────────────


def check_postgres_installed() -> bool:
    """Check if PostgreSQL binaries are available on PATH."""
    return shutil.which("pg_ctl") is not None


def is_initialized() -> bool:
    """Check if data directory exists and is initialized."""
    return (get_pgdata() / "PG_VERSION").exists()


def is_running() -> bool:
    """Check if PostgreSQL is running."""
    result = subprocess.run(
        ["pg_ctl", "-D", str(get_pgdata()), "status"],
        capture_output=True,
    )
    return result.returncode == 0


def init_db() -> None:
    """Initialize the data directory + create sensei database."""
    logger.info("Initializing PostgreSQL data directory...")
    get_sensei_home().mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["initdb", "-D", str(get_pgdata()), "--auth=trust", "--no-instructions"],
        check=True,
    )

    start()

    # Create database (uses Unix socket)
    subprocess.run(
        ["createdb", "-h", str(get_pgdata()), "sensei"],
        check=True,
    )
    logger.info("PostgreSQL initialized and sensei database created")


def start() -> None:
    """Start PostgreSQL (blocking until ready)."""
    logger.info("Starting PostgreSQL...")
    subprocess.run(
        [
            "pg_ctl",
            "-D",
            str(get_pgdata()),
            "-l",
            str(get_pg_log()),
            "-o",
            f"-k {get_pgdata()}",  # Unix socket in pgdata
            "start",
            "-w",
        ],
        check=True,
    )
    logger.info("PostgreSQL started")


def stop() -> None:
    """Stop PostgreSQL."""
    if is_running():
        logger.info("Stopping PostgreSQL...")
        subprocess.run(
            ["pg_ctl", "-D", str(get_pgdata()), "stop", "-m", "fast"],
            check=True,
        )
        logger.info("PostgreSQL stopped")


# ─────────────────────────────────────────────────────────────────────────────
# Migrations (local mode only) - thin wrapper on alembic
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_migrated() -> None:
    """Run alembic migrations."""
    import asyncio
    from functools import partial

    from alembic import command
    from alembic.config import Config

    from sensei.settings import sensei_settings

    # Build alembic config programmatically (works when installed as package)
    config = Config()
    config.set_main_option("script_location", "sensei:migrations")
    # env.py uses async_engine_from_config, so keep +asyncpg in URL
    config.set_main_option("sqlalchemy.url", sensei_settings.database_url)

    # Run migrations (sync operation, run in thread pool)
    logger.info("Running database migrations...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(command.upgrade, config, "head"))
    logger.info("Database migrations complete")


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_db_ready() -> None:
    """Ensure database is ready for use.

    **Idempotent** - safe to call multiple times. Uses module-level flag
    to skip work on subsequent calls (e.g., when called from both
    combined_lifespan and individual service lifespans).

    Behavior matrix:
    | DATABASE_URL | auto_migrate | Behavior                              |
    |--------------|--------------|---------------------------------------|
    | Not set      | True         | Start PG, migrate                     |
    | Not set      | False        | Warn, ignore, start PG, migrate anyway|
    | Set          | True         | Connect, migrate                      |
    | Set          | False        | Connect only                          |
    """
    global _db_ready

    if _db_ready:
        logger.debug("ensure_db_ready() already completed, skipping")
        return

    from sensei.settings import sensei_settings

    should_migrate = sensei_settings.database_auto_migrate

    if not sensei_settings.is_external_database:
        # Sensei-managed mode - must migrate regardless of setting
        if not should_migrate:
            logger.warning(
                "database_auto_migrate=False ignored for sensei-managed database; "
                "migrations are required when sensei manages PostgreSQL"
            )
            should_migrate = True

        if not check_postgres_installed():
            raise BrokenInvariant(
                "PostgreSQL not found. Please install PostgreSQL 17+:\n"
                "  macOS:   brew install postgresql@17\n"
                "  Ubuntu:  sudo apt install postgresql-17\n"
                "  Windows: https://www.postgresql.org/download/windows/"
            )

        if not is_initialized():
            try:
                init_db()
            except subprocess.CalledProcessError:
                # Another process may have initialized - check again
                if not is_initialized():
                    raise  # Real failure
        elif not is_running():
            start()  # pg_ctl start is safe to call concurrently

    if should_migrate:
        await ensure_migrated()

    _db_ready = True
    logger.info("Database ready")
