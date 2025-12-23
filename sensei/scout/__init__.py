"""Scout: GitHub repository exploration tools.

Scout provides MCP tools to explore any public GitHub repository:
- repo_map: Structural map of symbols (classes, functions, signatures)
- glob: Find files by pattern
- read: Read file contents
- grep: Search for patterns
- tree: Directory structure

All tools accept a GitHub URL and optional ref (branch/tag/commit).
Repos are cloned to a local cache (~/.scout/repos) with automatic
staleness handling for branches.

All file discovery uses ripgrep/lstr which respect .gitignore by default.

Usage as MCP server:
    from sensei.scout import mcp
    mcp.run()  # stdio transport
    # or
    app = mcp.http_app(path="/scout")  # HTTP transport

Usage as library:
    from sensei.scout import with_repo, glob_files, grep_files

    async with with_repo("https://github.com/org/repo", "main") as path:
        files = await glob_files(path, "**/*.py")
        result = await grep_files(path, "async def")
"""

from .manager import RepoManager, get_manager, with_repo
from .models import RepoMeta, RepoRef
from .operations import (
    TreeResult,
    build_tree,
    glob_files,
    grep_files,
    list_files,
    read_files,
)

# DISABLED: aider-chat conflicts with pydantic-ai (openai version mismatch)
# from .repomap import RepoMapWrapper, generate_repo_map

from .server import main, mcp

__all__ = [
    # Server
    "mcp",
    "main",
    # Manager
    "RepoManager",
    "get_manager",
    "with_repo",
    # Models
    "RepoRef",
    "RepoMeta",
    # Operations
    "glob_files",
    "read_files",
    "grep_files",
    "build_tree",
    "list_files",
    "TreeResult",
    # DISABLED: aider-chat conflicts with pydantic-ai (openai version mismatch)
    # "RepoMapWrapper",
    # "generate_repo_map",
]
