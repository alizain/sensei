"""Wrapper for Aider's RepoMap functionality.

DISABLED: aider-chat conflicts with pydantic-ai due to openai version mismatch.
- aider-chat pins openai==1.99.1
- pydantic-ai requires openai>=1.107.2

Re-enable when aider-chat updates its openai dependency.

Provides a clean interface to generate structural maps of repositories
using Aider's tree-sitter based symbol extraction and ranking.
"""

# from __future__ import annotations
#
# from pathlib import Path
#
# import tiktoken
# from aider.repomap import RepoMap
#
# from sensei.types import NoResults, Success
#
#
# class _RepoMapIO:
# 	"""Minimal IO stub for Aider's RepoMap.
#
# 	RepoMap expects an IO object with these methods for logging
# 	and file reading. We silence logging and provide basic file reading.
# 	"""
#
# 	def tool_output(self, *args, **kwargs) -> None:
# 		pass
#
# 	def tool_error(self, *args, **kwargs) -> None:
# 		pass
#
# 	def tool_warning(self, *args, **kwargs) -> None:
# 		pass
#
# 	def read_text(self, path: str) -> str:
# 		return Path(path).read_text(encoding="utf-8", errors="replace")
#
#
# class _RepoMapModel:
# 	"""Minimal model stub for token counting.
#
# 	RepoMap uses this to estimate token usage and stay within budget.
# 	"""
#
# 	def __init__(self):
# 		self._enc = tiktoken.get_encoding("cl100k_base")
#
# 	def token_count(self, text: str) -> int:
# 		return len(self._enc.encode(text)) if text else 0
#
#
# class RepoMapWrapper:
# 	"""Wrapper to use Aider's RepoMap as a standalone library.
#
# 	Generates a structural map of a repository showing:
# 	- Classes and their methods
# 	- Functions with signatures
# 	- Symbols ranked by importance (using PageRank on the dependency graph)
#
# 	Example output:
# 	    src/core.py:
# 	    ⋮
# 	    │class Engine:
# 	    │    def __init__(self, config: Config):
# 	    │    async def run(self) -> Result:
# 	    ⋮
# 	    src/utils.py:
# 	    │def parse_config(path: str) -> Config:
# 	"""
#
# 	def __init__(self, root: str, map_tokens: int = 2048):
# 		"""Initialize the RepoMap wrapper.
#
# 		Args:
# 		    root: Path to the repository root
# 		    map_tokens: Maximum tokens for the generated map
# 		"""
# 		self._rm = RepoMap(
# 			map_tokens=map_tokens,
# 			root=root,
# 			main_model=_RepoMapModel(),
# 			io=_RepoMapIO(),
# 			verbose=False,
# 		)
#
# 	def get_map(self, files: list[str]) -> str:
# 		"""Generate a repository map for the given files.
#
# 		Args:
# 		    files: List of absolute file paths to include
#
# 		Returns:
# 		    Formatted repository map string, or empty string if no symbols found
# 		"""
# 		return self._rm.get_repo_map(chat_files=[], other_files=files) or ""
#
#
# def generate_repo_map(root: Path, files: list[Path], max_tokens: int = 2048) -> Success[str] | NoResults:
# 	"""Generate a repository map for the given files.
#
# 	Convenience function that wraps RepoMapWrapper.
#
# 	Args:
# 	    root: Repository root path
# 	    files: List of source file paths (absolute)
# 	    max_tokens: Maximum tokens for the map
#
# 	Returns:
# 	    Success with formatted repository map string, or NoResults if no symbols found
# 	"""
# 	if not files:
# 		return NoResults()
#
# 	wrapper = RepoMapWrapper(root=str(root), map_tokens=max_tokens)
# 	result = wrapper.get_map(files=[str(f) for f in files])
#
# 	if not result:
# 		return NoResults()
#
# 	return Success(result)
