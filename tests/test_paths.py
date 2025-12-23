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


def test_get_scout_repos():
    """Returns sensei_home/scout/repos."""
    from sensei.paths import get_scout_repos, get_sensei_home

    assert get_scout_repos() == get_sensei_home() / "scout" / "repos"
