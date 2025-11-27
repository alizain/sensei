"""Tests for Scout repository exploration tools.

Testing Strategy:
- Unit tests: Pure functions (models, read_files) using tmp_path fixtures
- Integration tests: Operations requiring external tools (rg, lstr, git)
- Slow tests: Manager tests that clone real repos (marked with pytest.mark.slow)

Run all tests: uv run pytest tests/test_scout.py -v
Run fast only:  uv run pytest tests/test_scout.py -v -m "not slow"
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sensei.scout.models import RepoMeta, RepoRef


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
	"""Create a temporary git repository for testing gitignore behavior."""
	subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
	subprocess.run(
		["git", "config", "user.email", "test@test.com"],
		cwd=tmp_path,
		capture_output=True,
		check=True,
	)
	subprocess.run(
		["git", "config", "user.name", "Test"],
		cwd=tmp_path,
		capture_output=True,
		check=True,
	)
	return tmp_path


# ─────────────────────────────────────────────────────────────────────────────
# Models: RepoRef
# ─────────────────────────────────────────────────────────────────────────────


class TestRepoRef:
	"""Tests for RepoRef URL parsing and properties."""

	def test_parse_basic_url(self):
		ref = RepoRef.parse("https://github.com/anthropics/anthropic-cookbook")
		assert ref.host == "github.com"
		assert ref.owner == "anthropics"
		assert ref.repo == "anthropic-cookbook"
		assert ref.ref is None

	def test_parse_url_with_ref(self):
		ref = RepoRef.parse("https://github.com/anthropics/anthropic-cookbook", "main")
		assert ref.ref == "main"

	def test_parse_url_with_git_suffix(self):
		ref = RepoRef.parse("https://github.com/org/repo.git")
		assert ref.repo == "repo"

	def test_parse_url_with_trailing_slash(self):
		ref = RepoRef.parse("https://github.com/org/repo/")
		assert ref.repo == "repo"

	def test_parse_invalid_url_raises(self):
		with pytest.raises(ValueError, match="Invalid GitHub URL"):
			RepoRef.parse("not-a-url")

	def test_parse_other_hosts_accepted(self):
		# RepoRef accepts any git host, not just GitHub
		ref = RepoRef.parse("https://gitlab.com/org/repo")
		assert ref.host == "gitlab.com"
		assert ref.owner == "org"
		assert ref.repo == "repo"

	def test_parse_incomplete_url_raises(self):
		with pytest.raises(ValueError, match="Invalid GitHub URL"):
			RepoRef.parse("https://github.com/only-owner")

	def test_cache_key_without_ref(self):
		ref = RepoRef.parse("https://github.com/org/repo")
		assert ref.cache_key == "HEAD"

	def test_cache_key_with_ref(self):
		ref = RepoRef.parse("https://github.com/org/repo", "v1.0.0")
		assert ref.cache_key == "v1.0.0"

	def test_clone_url(self):
		ref = RepoRef.parse("https://github.com/anthropics/anthropic-cookbook")
		assert ref.clone_url == "https://github.com/anthropics/anthropic-cookbook.git"


# ─────────────────────────────────────────────────────────────────────────────
# Models: RepoMeta
# ─────────────────────────────────────────────────────────────────────────────


class TestRepoMeta:
	"""Tests for RepoMeta staleness logic and serialization."""

	def test_branch_is_stale_after_max_age(self):
		old_time = datetime.now() - timedelta(hours=2)
		meta = RepoMeta(cloned_at=old_time, commit_sha="abc123", ref_type="branch")
		assert meta.is_stale(timedelta(hours=1)) is True

	def test_branch_is_fresh_within_max_age(self):
		recent_time = datetime.now() - timedelta(minutes=30)
		meta = RepoMeta(cloned_at=recent_time, commit_sha="abc123", ref_type="branch")
		assert meta.is_stale(timedelta(hours=1)) is False

	def test_tag_never_stale(self):
		old_time = datetime.now() - timedelta(days=30)
		meta = RepoMeta(cloned_at=old_time, commit_sha="abc123", ref_type="tag")
		assert meta.is_stale(timedelta(hours=1)) is False

	def test_commit_never_stale(self):
		old_time = datetime.now() - timedelta(days=30)
		meta = RepoMeta(cloned_at=old_time, commit_sha="abc123", ref_type="commit")
		assert meta.is_stale(timedelta(hours=1)) is False

	def test_to_dict_and_from_dict_roundtrip(self):
		original = RepoMeta(
			cloned_at=datetime(2024, 1, 15, 10, 30, 0),
			commit_sha="abc123def456",
			ref_type="branch",
		)
		data = original.to_dict()
		restored = RepoMeta.from_dict(data)

		assert restored.commit_sha == original.commit_sha
		assert restored.ref_type == original.ref_type
		assert restored.cloned_at == original.cloned_at


# ─────────────────────────────────────────────────────────────────────────────
# Operations: read_files (async but pure, no external tools)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReadFiles:
	"""Tests for read_files operation using tmp_path fixtures."""

	async def test_read_single_file(self, tmp_path: Path):
		from sensei.scout.operations import read_files

		# Create test file
		test_file = tmp_path / "test.txt"
		test_file.write_text("hello world")

		result = await read_files(tmp_path, ["test.txt"])
		assert len(result.data) == 1
		assert result.data[0].path == "test.txt"
		assert result.data[0].content == "hello world"
		assert result.data[0].error is None

	async def test_read_multiple_files(self, tmp_path: Path):
		from sensei.scout.operations import read_files

		(tmp_path / "a.txt").write_text("file a")
		(tmp_path / "b.txt").write_text("file b")

		result = await read_files(tmp_path, ["a.txt", "b.txt"])
		assert len(result.data) == 2
		assert result.data[0].content == "file a"
		assert result.data[1].content == "file b"

	async def test_read_missing_file(self, tmp_path: Path):
		from sensei.scout.operations import read_files

		result = await read_files(tmp_path, ["missing.txt"])
		assert len(result.data) == 1
		assert result.data[0].error == "File not found"
		assert result.data[0].content is None

	async def test_read_directory_returns_error(self, tmp_path: Path):
		from sensei.scout.operations import read_files

		subdir = tmp_path / "subdir"
		subdir.mkdir()

		result = await read_files(tmp_path, ["subdir"])
		assert len(result.data) == 1
		assert result.data[0].error == "Not a file"

	async def test_read_truncates_large_file(self, tmp_path: Path):
		from sensei.scout.operations import read_files

		large_file = tmp_path / "large.txt"
		large_file.write_text("x" * 200_000)

		result = await read_files(tmp_path, ["large.txt"], max_size=1000)
		assert len(result.data) == 1
		assert len(result.data[0].content) < 200_000
		assert "truncated" in result.data[0].content

	async def test_read_nested_path(self, tmp_path: Path):
		from sensei.scout.operations import read_files

		nested = tmp_path / "src" / "lib"
		nested.mkdir(parents=True)
		(nested / "util.py").write_text("def foo(): pass")

		result = await read_files(tmp_path, ["src/lib/util.py"])
		assert result.data[0].content == "def foo(): pass"


# ─────────────────────────────────────────────────────────────────────────────
# Operations: Integration tests (require rg, lstr)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGlobFiles:
	"""Tests for glob_files using ripgrep."""

	async def test_glob_python_files(self, tmp_path: Path):
		from sensei.scout.operations import glob_files

		(tmp_path / "main.py").write_text("# main")
		(tmp_path / "test.py").write_text("# test")
		(tmp_path / "readme.md").write_text("# readme")

		result = await glob_files(tmp_path, "*.py")
		names = {p.name for p in result.data}
		assert names == {"main.py", "test.py"}

	async def test_glob_recursive(self, tmp_path: Path):
		from sensei.scout.operations import glob_files

		(tmp_path / "src").mkdir()
		(tmp_path / "src" / "lib.py").write_text("# lib")
		(tmp_path / "main.py").write_text("# main")

		result = await glob_files(tmp_path, "**/*.py")
		names = {p.name for p in result.data}
		assert names == {"main.py", "lib.py"}

	async def test_glob_no_matches(self, tmp_path: Path):
		from sensei.scout.operations import glob_files

		(tmp_path / "readme.md").write_text("# readme")

		result = await glob_files(tmp_path, "*.py")
		assert result.data == []

	async def test_glob_respects_gitignore(self, git_repo: Path):
		from sensei.scout.operations import glob_files

		(git_repo / ".gitignore").write_text("ignored/\n")
		(git_repo / "keep.py").write_text("# keep")
		ignored = git_repo / "ignored"
		ignored.mkdir()
		(ignored / "skip.py").write_text("# skip")

		result = await glob_files(git_repo, "**/*.py")
		names = {p.name for p in result.data}
		assert "keep.py" in names
		assert "skip.py" not in names


@pytest.mark.asyncio
class TestGrepFiles:
	"""Tests for grep_files using ripgrep."""

	async def test_grep_finds_pattern(self, tmp_path: Path):
		from sensei.scout.operations import grep_files
		from sensei.types import Success

		(tmp_path / "main.py").write_text("def hello():\n    return 'world'")

		result = await grep_files(tmp_path, "def hello", context_lines=0)
		assert isinstance(result, Success)
		assert result.data.match_count > 0
		assert "def hello" in result.data.output

	async def test_grep_no_matches(self, tmp_path: Path):
		from sensei.scout.operations import grep_files
		from sensei.types import NoResults

		(tmp_path / "main.py").write_text("def foo(): pass")

		result = await grep_files(tmp_path, "xyz_not_found")
		assert isinstance(result, NoResults)

	async def test_grep_with_glob_filter(self, tmp_path: Path):
		from sensei.scout.operations import grep_files
		from sensei.types import Success

		(tmp_path / "main.py").write_text("hello")
		(tmp_path / "main.js").write_text("hello")

		result = await grep_files(tmp_path, "hello", glob="*.py", context_lines=0)
		assert isinstance(result, Success)
		assert "main.py" in result.data.output
		assert "main.js" not in result.data.output

	async def test_grep_with_context_lines(self, tmp_path: Path):
		from sensei.scout.operations import grep_files
		from sensei.types import Success

		content = "line1\nline2\ntarget\nline4\nline5"
		(tmp_path / "test.txt").write_text(content)

		result = await grep_files(tmp_path, "target", context_lines=1)
		assert isinstance(result, Success)
		assert "line2" in result.data.output
		assert "line4" in result.data.output

	async def test_grep_respects_gitignore(self, git_repo: Path):
		from sensei.scout.operations import grep_files
		from sensei.types import Success

		(git_repo / ".gitignore").write_text("ignored/\n")
		(git_repo / "keep.py").write_text("searchme")
		ignored = git_repo / "ignored"
		ignored.mkdir()
		(ignored / "skip.py").write_text("searchme")

		result = await grep_files(git_repo, "searchme", context_lines=0)
		assert isinstance(result, Success)
		assert "keep.py" in result.data.output
		assert "skip.py" not in result.data.output


@pytest.mark.asyncio
class TestListFiles:
	"""Tests for list_files using ripgrep."""

	async def test_list_all_files(self, tmp_path: Path):
		from sensei.scout.operations import list_files

		(tmp_path / "a.py").write_text("")
		(tmp_path / "b.txt").write_text("")
		(tmp_path / "src").mkdir()
		(tmp_path / "src" / "c.py").write_text("")

		result = await list_files(tmp_path)
		names = {p.name for p in result.data}
		assert names == {"a.py", "b.txt", "c.py"}

	async def test_list_files_in_subpath(self, tmp_path: Path):
		from sensei.scout.operations import list_files

		(tmp_path / "root.py").write_text("")
		src = tmp_path / "src"
		src.mkdir()
		(src / "lib.py").write_text("")

		result = await list_files(tmp_path, "src")
		names = {p.name for p in result.data}
		assert names == {"lib.py"}
		assert "root.py" not in names

	async def test_list_files_respects_gitignore(self, git_repo: Path):
		from sensei.scout.operations import list_files

		(git_repo / ".gitignore").write_text("*.log\n")
		(git_repo / "keep.py").write_text("")
		(git_repo / "skip.log").write_text("")

		result = await list_files(git_repo)
		names = {p.name for p in result.data}
		assert "keep.py" in names
		assert "skip.log" not in names


@pytest.mark.asyncio
class TestBuildTree:
	"""Tests for build_tree using lstr."""

	async def test_tree_basic(self, tmp_path: Path):
		from sensei.scout.operations import build_tree
		from sensei.types import Success

		(tmp_path / "file.txt").write_text("")
		(tmp_path / "src").mkdir()
		(tmp_path / "src" / "main.py").write_text("")

		result = await build_tree(tmp_path, max_depth=2)
		assert isinstance(result, Success)
		assert "file.txt" in result.data.output
		assert "src" in result.data.output
		assert "main.py" in result.data.output

	async def test_tree_subpath(self, tmp_path: Path):
		from sensei.scout.operations import build_tree
		from sensei.types import Success

		(tmp_path / "root.txt").write_text("")
		src = tmp_path / "src"
		src.mkdir()
		(src / "lib.py").write_text("")

		result = await build_tree(tmp_path, subpath="src", max_depth=2)
		assert isinstance(result, Success)
		assert "lib.py" in result.data.output
		# root.txt should not appear since we're only showing src/
		assert "root.txt" not in result.data.output

	async def test_tree_missing_path(self, tmp_path: Path):
		from sensei.scout.operations import build_tree
		from sensei.types import ToolError

		with pytest.raises(ToolError, match="not found"):
			await build_tree(tmp_path, subpath="nonexistent")

	async def test_tree_file_not_directory(self, tmp_path: Path):
		from sensei.scout.operations import build_tree
		from sensei.types import ToolError

		(tmp_path / "file.txt").write_text("")

		with pytest.raises(ToolError, match="not a directory"):
			await build_tree(tmp_path, subpath="file.txt")

	async def test_tree_respects_gitignore(self, git_repo: Path):
		from sensei.scout.operations import build_tree
		from sensei.types import Success

		(git_repo / ".gitignore").write_text("ignored/\n")
		(git_repo / "keep.txt").write_text("")
		ignored = git_repo / "ignored"
		ignored.mkdir()
		(ignored / "skip.txt").write_text("")

		result = await build_tree(git_repo, max_depth=2)
		assert isinstance(result, Success)
		assert "keep.txt" in result.data.output
		assert "skip.txt" not in result.data.output


# ─────────────────────────────────────────────────────────────────────────────
# RepoMap: Integration tests (require aider)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRepoMap:
	"""Tests for repo_map generation using Aider's RepoMap."""

	async def test_generate_repo_map_finds_symbols(self, tmp_path: Path):
		from sensei.scout.operations import list_files
		from sensei.scout.repomap import generate_repo_map
		from sensei.types import Success

		# Create Python file with class and function
		(tmp_path / "main.py").write_text(
			"class Engine:\n    def run(self) -> None:\n        pass\n\ndef helper() -> str:\n    return 'help'\n"
		)

		files_result = await list_files(tmp_path)
		result = generate_repo_map(tmp_path, files_result.data, max_tokens=1024)

		assert isinstance(result, Success)
		assert "Engine" in result.data
		assert "run" in result.data
		assert "helper" in result.data

	async def test_generate_repo_map_empty_files(self, tmp_path: Path):
		from sensei.scout.repomap import generate_repo_map
		from sensei.types import NoResults

		result = generate_repo_map(tmp_path, [], max_tokens=1024)
		assert isinstance(result, NoResults)

	async def test_generate_repo_map_no_parseable_files(self, tmp_path: Path):
		from sensei.scout.operations import list_files
		from sensei.scout.repomap import generate_repo_map
		from sensei.types import NoResults, Success

		# Create non-source file that tree-sitter can't parse
		(tmp_path / "data.json").write_text('{"key": "value"}')

		files_result = await list_files(tmp_path)
		result = generate_repo_map(tmp_path, files_result.data, max_tokens=1024)
		# May return Success with empty output or NoResults since JSON isn't parsed for symbols
		assert isinstance(result, (Success, NoResults))


# ─────────────────────────────────────────────────────────────────────────────
# Manager: Integration tests (require git, network)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRepoManager:
	"""Tests for RepoManager cloning and caching. Uses octocat/Hello-World (tiny repo)."""

	async def test_acquire_clones_repo(self, tmp_path: Path):
		from sensei.scout.manager import RepoManager

		manager = RepoManager(cache_dir=tmp_path)

		# Use a tiny repo (< 100KB)
		path = await manager.acquire(
			"https://github.com/octocat/Hello-World",
			ref="master",
		)
		try:
			assert path.exists()
			assert (path / ".git").exists()
			assert (path / ".scout_meta.json").exists()
		finally:
			manager.release(path)

	async def test_acquire_uses_cache(self, tmp_path: Path):
		from sensei.scout.manager import RepoManager

		manager = RepoManager(cache_dir=tmp_path, branch_max_age=timedelta(hours=1))

		# First acquire - clones
		path1 = await manager.acquire(
			"https://github.com/octocat/Hello-World",
			ref="master",
		)
		manager.release(path1)

		# Second acquire - should use cache
		path2 = await manager.acquire(
			"https://github.com/octocat/Hello-World",
			ref="master",
		)
		manager.release(path2)

		assert path1 == path2

	async def test_with_repo_context_manager(self, tmp_path: Path):
		from sensei.scout.manager import RepoManager, with_repo

		# Reset global manager to use our tmp_path
		import sensei.scout.manager as manager_module

		old_manager = manager_module._manager
		manager_module._manager = RepoManager(cache_dir=tmp_path)

		try:
			async with with_repo("https://github.com/octocat/Hello-World", "master") as path:
				assert path.exists()
				assert (path / ".git").exists()
		finally:
			manager_module._manager = old_manager
