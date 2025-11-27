"""Data models for Scout repository exploration.

Pure data structures with no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse


@dataclass
class RepoRef:
	"""Parsed repository reference."""

	host: str  # github.com
	owner: str  # anthropics
	repo: str  # anthropic-cookbook
	ref: str | None  # main, v1.0.0, abc123...

	@classmethod
	def parse(cls, url: str, ref: str | None = None) -> RepoRef:
		"""Parse GitHub URL into components.

		Args:
		    url: GitHub repo URL (e.g., https://github.com/org/repo)
		    ref: Optional branch, tag, or commit SHA

		Returns:
		    RepoRef with parsed components

		Raises:
		    ValueError: If URL is not a valid GitHub repo URL
		"""
		parsed = urlparse(url)
		parts = parsed.path.strip("/").split("/")
		if len(parts) < 2:
			raise ValueError(f"Invalid GitHub URL: {url}")
		return cls(
			host=parsed.netloc,
			owner=parts[0],
			repo=parts[1].removesuffix(".git"),
			ref=ref,
		)

	@property
	def cache_key(self) -> str:
		"""Directory name for this ref in cache."""
		return self.ref or "HEAD"

	@property
	def clone_url(self) -> str:
		"""Git clone URL."""
		return f"https://{self.host}/{self.owner}/{self.repo}.git"


@dataclass
class RepoMeta:
	"""Metadata stored in .scout_meta.json for a cached repo."""

	cloned_at: datetime
	commit_sha: str
	ref_type: str  # "branch" | "tag" | "commit"

	def is_stale(self, max_age: timedelta) -> bool:
		"""Check if this ref is stale and needs re-cloning.

		Tags and commits are immutable, so never stale.
		Branches are stale if cloned_at exceeds max_age.
		"""
		if self.ref_type in ("tag", "commit"):
			return False
		return datetime.now() - self.cloned_at > max_age

	def to_dict(self) -> dict:
		"""Serialize to JSON-compatible dict."""
		return {
			"cloned_at": self.cloned_at.isoformat(),
			"commit_sha": self.commit_sha,
			"ref_type": self.ref_type,
		}

	@classmethod
	def from_dict(cls, data: dict) -> RepoMeta:
		"""Deserialize from JSON dict."""
		return cls(
			cloned_at=datetime.fromisoformat(data["cloned_at"]),
			commit_sha=data["commit_sha"],
			ref_type=data["ref_type"],
		)
