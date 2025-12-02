"""Tests for sensei.paths module."""

import os
from pathlib import Path
from unittest.mock import patch


def test_get_sensei_home_default():
    """Returns ~/.sensei when SENSEI_HOME not set."""
    with patch.dict(os.environ, {}, clear=False):
        # Remove SENSEI_HOME if present
        os.environ.pop("SENSEI_HOME", None)
        from sensei.paths import get_sensei_home

        assert get_sensei_home() == Path.home() / ".sensei"


def test_get_sensei_home_from_env(tmp_path):
    """Respects SENSEI_HOME env var."""
    with patch.dict(os.environ, {"SENSEI_HOME": str(tmp_path)}):
        from sensei.paths import get_sensei_home

        assert get_sensei_home() == tmp_path


def test_get_pgdata():
    """Returns sensei_home/pgdata."""
    from sensei.paths import get_pgdata, get_sensei_home

    assert get_pgdata() == get_sensei_home() / "pgdata"


def test_get_pg_log():
    """Returns sensei_home/pg.log."""
    from sensei.paths import get_pg_log, get_sensei_home

    assert get_pg_log() == get_sensei_home() / "pg.log"


def test_get_scout_repos():
    """Returns sensei_home/scout/repos."""
    from sensei.paths import get_scout_repos, get_sensei_home

    assert get_scout_repos() == get_sensei_home() / "scout" / "repos"


def test_get_local_database_url():
    """Returns Unix socket URL pointing to pgdata."""
    from sensei.paths import get_local_database_url, get_pgdata

    url = get_local_database_url()
    assert url.startswith("postgresql+asyncpg:///sensei?host=")
    assert str(get_pgdata()) in url
