"""Tests for sensei.database.local module."""

import shutil
from unittest.mock import AsyncMock, patch

import pytest


def test_check_postgres_installed_true():
    """Returns True when pg_ctl found."""
    with patch.object(shutil, "which", return_value="/usr/bin/pg_ctl"):
        from sensei.database.local import check_postgres_installed

        assert check_postgres_installed() is True


def test_check_postgres_not_installed():
    """Returns False when pg_ctl not found."""
    with patch.object(shutil, "which", return_value=None):
        from sensei.database.local import check_postgres_installed

        assert check_postgres_installed() is False


def test_is_initialized_false_when_no_pgdata(tmp_path):
    """Returns False when PG_VERSION doesn't exist."""
    with patch("sensei.database.local.get_pgdata", return_value=tmp_path / "pgdata"):
        from sensei.database.local import is_initialized

        assert is_initialized() is False


def test_is_initialized_true_when_pg_version_exists(tmp_path):
    """Returns True when PG_VERSION exists."""
    pgdata = tmp_path / "pgdata"
    pgdata.mkdir()
    (pgdata / "PG_VERSION").write_text("17")

    with patch("sensei.database.local.get_pgdata", return_value=pgdata):
        from sensei.database.local import is_initialized

        assert is_initialized() is True


@pytest.mark.asyncio
async def test_ensure_db_ready_skips_for_external_db():
    """External database skips all PostgreSQL management."""
    import sensei.database.local as local

    # Reset the flag
    local._db_ready = False

    mock_settings = type("MockSettings", (), {"is_external_database": True})()

    with (
        patch("sensei.config.settings", mock_settings),
        patch.object(local, "check_postgres_installed") as mock_check,
    ):
        await local.ensure_db_ready()

        # Should not check for postgres when external DB
        mock_check.assert_not_called()
        assert local._db_ready is True


@pytest.mark.asyncio
async def test_ensure_db_ready_idempotent():
    """Second call is a no-op due to _db_ready flag."""
    import sensei.database.local as local

    # Reset the flag
    local._db_ready = False

    mock_settings = type("MockSettings", (), {"is_external_database": False})()

    with (
        patch("sensei.config.settings", mock_settings),
        patch.object(local, "check_postgres_installed", return_value=True),
        patch.object(local, "is_initialized", return_value=True),
        patch.object(local, "is_running", return_value=True),
        patch.object(local, "ensure_migrated", new_callable=AsyncMock) as mock_migrate,
    ):
        # First call does work
        await local.ensure_db_ready()
        assert local._db_ready is True
        mock_migrate.assert_called_once()

        # Second call skips
        mock_migrate.reset_mock()
        await local.ensure_db_ready()
        mock_migrate.assert_not_called()
