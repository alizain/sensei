"""Repository manager for cloning, caching, and locking.

Handles the lifecycle of cloned repositories:
- Shallow cloning from GitHub
- Cache management with staleness detection
- In-memory locking for concurrent access
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator

from sensei.types import ToolError, TransientError

from .models import RepoMeta, RepoRef

logger = logging.getLogger(__name__)


class RepoManager:
	"""Manages cloned repository cache with locking."""

	def __init__(
		self,
		cache_dir: Path | None = None,
		branch_max_age: timedelta = timedelta(hours=1),
	):
		"""Initialize the repository manager.

		Args:
		    cache_dir: Directory for cached repos. Defaults to current directory
		    branch_max_age: How long before branches are considered stale
		"""
		self.cache_dir = cache_dir or Path(".") / ".scout" / "repos"
		self.branch_max_age = branch_max_age
		self._locks: dict[str, asyncio.Lock] = {}

	def _get_lock(self, path: str) -> asyncio.Lock:
		"""Get or create lock for a repo path."""
		if path not in self._locks:
			self._locks[path] = asyncio.Lock()
		return self._locks[path]

	def _repo_path(self, ref: RepoRef) -> Path:
		"""Get cache path for a repo ref."""
		return self.cache_dir / ref.host / ref.owner / ref.repo / ref.cache_key

	async def acquire(self, url: str, ref: str | None = None) -> Path:
		"""Get path to cloned repo, cloning if needed.

		Acquires a lock on the repo path. Caller must call release() when done,
		or use the with_repo() context manager.

		Args:
		    url: GitHub repo URL
		    ref: Optional branch, tag, or commit SHA

		Returns:
		    Path to the cloned repository

		Raises:
		    ToolError: If URL is invalid or clone fails due to bad ref
		    TransientError: If clone fails due to network issues
		"""
		try:
			repo_ref = RepoRef.parse(url, ref)
		except ValueError as e:
			raise ToolError(str(e)) from e
		path = self._repo_path(repo_ref)
		lock = self._get_lock(str(path))

		await lock.acquire()

		try:
			meta_file = path / ".scout_meta.json"

			# Check if exists and not stale
			if path.exists() and meta_file.exists():
				meta = self._load_meta(meta_file)
				if not meta.is_stale(self.branch_max_age):
					logger.debug(f"Using cached repo: {path}")
					return path
				# Stale - remove and re-clone
				logger.info(f"Repo stale, re-cloning: {path}")
				shutil.rmtree(path)

			# Clone
			await self._clone(repo_ref, path)
			return path

		except Exception:
			lock.release()
			raise

	def release(self, path: Path) -> None:
		"""Release lock on a repo path."""
		lock = self._locks.get(str(path))
		if lock and lock.locked():
			lock.release()

	async def _clone(self, ref: RepoRef, path: Path) -> None:
		"""Shallow clone a repo.

		Raises:
		    ToolError: If clone fails due to bad ref, repo not found, etc.
		    TransientError: If clone fails due to network issues
		"""
		path.parent.mkdir(parents=True, exist_ok=True)

		cmd = ["git", "clone", "--depth", "1"]

		if ref.ref:
			cmd.extend(["--branch", ref.ref])

		cmd.extend([ref.clone_url, str(path)])

		logger.info(f"Cloning {ref.clone_url} (ref={ref.ref}) to {path}")

		proc = await asyncio.create_subprocess_exec(
			*cmd,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)
		_, stderr = await proc.communicate()

		if proc.returncode != 0:
			error_msg = stderr.decode()
			# Clean up partial clone
			if path.exists():
				shutil.rmtree(path)

			# Classify the error
			if "Could not resolve host" in error_msg or "Connection refused" in error_msg:
				raise TransientError(f"Network error cloning {ref.clone_url}: {error_msg}")
			else:
				# Bad ref, repo not found, auth required, etc.
				raise ToolError(f"Clone failed for {ref.clone_url}: {error_msg}")

		# Get commit SHA and ref type
		commit_sha = await self._get_commit_sha(path)
		ref_type = await self._detect_ref_type(ref, path)

		# Write metadata
		meta = RepoMeta(
			cloned_at=datetime.now(),
			commit_sha=commit_sha,
			ref_type=ref_type,
		)
		self._save_meta(path / ".scout_meta.json", meta)

		logger.info(f"Cloned successfully: {commit_sha[:8]} ({ref_type})")

	async def _get_commit_sha(self, path: Path) -> str:
		"""Get the current commit SHA."""
		proc = await asyncio.create_subprocess_exec(
			"git",
			"-C",
			str(path),
			"rev-parse",
			"HEAD",
			stdout=asyncio.subprocess.PIPE,
		)
		stdout, _ = await proc.communicate()
		return stdout.decode().strip()

	async def _detect_ref_type(self, ref: RepoRef, path: Path) -> str:
		"""Detect whether ref is a branch, tag, or commit."""
		if not ref.ref:
			return "branch"  # HEAD is a branch

		# Check if it looks like a commit SHA (40 hex chars)
		if len(ref.ref) >= 40 and all(c in "0123456789abcdef" for c in ref.ref[:40].lower()):
			return "commit"

		# Check if it's a tag
		proc = await asyncio.create_subprocess_exec(
			"git",
			"-C",
			str(path),
			"tag",
			"-l",
			ref.ref,
			stdout=asyncio.subprocess.PIPE,
		)
		stdout, _ = await proc.communicate()
		if stdout.decode().strip():
			return "tag"

		return "branch"

	def _load_meta(self, path: Path) -> RepoMeta:
		"""Load metadata from .scout_meta.json."""
		data = json.loads(path.read_text())
		return RepoMeta.from_dict(data)

	def _save_meta(self, path: Path, meta: RepoMeta) -> None:
		"""Save metadata to .scout_meta.json."""
		path.write_text(json.dumps(meta.to_dict(), indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Global Manager & Context Manager
# ─────────────────────────────────────────────────────────────────────────────

_manager: RepoManager | None = None


def get_manager() -> RepoManager:
	"""Get the global RepoManager instance."""
	global _manager
	if _manager is None:
		_manager = RepoManager()
	return _manager


@asynccontextmanager
async def with_repo(url: str, ref: str | None) -> AsyncGenerator[Path, None]:
	"""Context manager that acquires and releases repo lock.

	Usage:
	    async with with_repo("https://github.com/org/repo", "main") as path:
	        # path is a Path to the cloned repo
	        # lock is held for the duration
	"""
	manager = get_manager()
	path = await manager.acquire(url, ref)
	try:
		yield path
	finally:
		manager.release(path)
