"""Centralized path management for sensei.

This module handles all path detection and management. Uses SENSEI_HOME
environment variable with ~/.sensei default.

For development, set SENSEI_HOME=.sensei in .env to keep data local to the repo.
"""

import os
from pathlib import Path


def get_sensei_home() -> Path:
    """Get the sensei home directory.

    Priority:
    1. SENSEI_HOME env var (explicit override)
    2. ~/.sensei (default)

    For development, set SENSEI_HOME=.sensei in .env
    """
    if env_home := os.environ.get("SENSEI_HOME"):
        return Path(env_home)
    return Path.home() / ".sensei"


def get_pgdata() -> Path:
    """Get PostgreSQL data directory path."""
    return get_sensei_home() / "pgdata"


def get_pg_log() -> Path:
    """Get PostgreSQL log file path."""
    return get_sensei_home() / "pg.log"


def get_scout_repos() -> Path:
    """Get scout repository cache directory."""
    return get_sensei_home() / "scout" / "repos"


def get_local_database_url() -> str:
    """Get connection URL for local PostgreSQL using Unix socket.

    This is the default database URL when DATABASE_URL is not set.
    Uses Unix socket to avoid port conflicts with system PostgreSQL.
    """
    return f"postgresql+asyncpg:///sensei?host={get_pgdata()}"
