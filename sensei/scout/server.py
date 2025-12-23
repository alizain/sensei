"""FastMCP server for Scout repository exploration tools.

This is the edge layer that:
1. Validates and parses MCP tool inputs
2. Acquires repos via the manager
3. Calls core operations
4. Formats outputs for MCP
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from sensei.cli import run_server
from sensei.types import NoResults, Success

from .manager import with_repo
from .operations import (
    build_tree,
    glob_files,
    grep_files,
    read_files,
)

# DISABLED: aider-chat conflicts with pydantic-ai (openai version mismatch)
# from .operations import list_files
# from .repomap import generate_repo_map

logger = logging.getLogger(__name__)

REPO_URL_FIELD = Field(description="GitHub repo URL (e.g., https://github.com/org/repo)")
REPO_REF_FIELD = Field(description="Branch, tag, or commit SHA. Defaults to repo's default branch")
REPO_PATH_FIELD = Field(description="Subdirectory to map (defaults to repo root)")

# ─────────────────────────────────────────────────────────────────────────────
# FastMCP Server
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(name="scout")


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


# DISABLED: aider-chat conflicts with pydantic-ai (openai version mismatch)
# Re-enable when aider-chat updates its openai dependency.
#
# @scout.tool
# async def repo_map(
# 	url: Annotated[str, REPO_URL_FIELD],
# 	ref: Annotated[str | None, REPO_REF_FIELD] = None,
# 	path: Annotated[str, REPO_PATH_FIELD] = "",
# 	max_tokens: Annotated[int, Field(description="Max tokens for the map", ge=256, le=8192)] = 2048,
# ) -> str:
# 	"""Get a structural map of the repository showing key classes, functions, and their signatures.
#
# 	Use this first to understand a codebase's architecture before diving into specific files.
# 	Returns symbols ranked by importance within the token budget.
#
# 	The map shows:
# 	- Class and function definitions with signatures
# 	- File organization
# 	- Key symbols ranked by how often they're referenced
#
# 	Example output:
# 	    src/core.py:
# 	    │class Engine:
# 	    │    def __init__(self, config: Config):
# 	    │    async def run(self) -> Result:
# 	    ⋮
# 	    src/utils.py:
# 	    │def parse_config(path: str) -> Config:
# 	"""
# 	async with with_repo(url, ref) as repo_path:
# 		match await list_files(repo_path, path):
# 			case Success(files) if not files:
# 				return f"No files found in '{path or 'repository'}'."
# 			case Success(files):
# 				pass
#
# 		logger.info(f"Generating repo map for {len(files)} files")
#
# 		match generate_repo_map(repo_path, files, max_tokens):
# 			case Success(result):
# 				return result
# 			case NoResults():
# 				return "No symbols found (no parseable source files)."


@mcp.tool
async def glob(
    url: Annotated[str, REPO_URL_FIELD],
    pattern: Annotated[str, Field(description="Glob pattern (e.g., '**/*.py', 'src/**/*.ts')")],
    ref: Annotated[str | None, REPO_REF_FIELD] = None,
) -> str:
    """Find files matching a glob pattern in an external GitHub repository.

    Use this to explore repos you don't have locally. Scout clones the repo to a
    temp directory. Specify a ref (branch/tag/commit) to get a specific version,
    or omit it to use the repo's default branch (usually main/master).

    Returns relative file paths, sorted alphabetically. Limited to 500 results.

    Examples:
        - "**/*.py" - all Python files
        - "src/**/*.ts" - TypeScript files in src/
        - "*.md" - Markdown files in root
        - "tests/test_*.py" - test files
    """
    async with with_repo(url, ref) as path:
        match await glob_files(path, pattern):
            case Success(matches) if not matches:
                return f"No files matching '{pattern}'"
            case Success(matches):
                pass

        # Limit and format
        total = len(matches)
        matches = matches[:500]
        lines = [str(m.relative_to(path)) for m in matches]

        if total > 500:
            lines.append(f"\n... and {total - 500} more files")

        return "\n".join(lines)


@mcp.tool
async def read(
    url: Annotated[str, REPO_URL_FIELD],
    paths: Annotated[list[str], Field(description="File path(s) relative to repo root")],
    ref: Annotated[str | None, REPO_REF_FIELD] = None,
) -> str:
    """Read one or more files from an external GitHub repository.

    Use this to examine source code, configs, or docs in repos you don't have
    locally. Scout clones the repo to a temp directory. Specify a ref
    (branch/tag/commit) to get a specific version, or omit it to use the repo's
    default branch (usually main/master).

    Returns file contents with path headers. Large files (>100KB) are truncated.
    Binary files return an error message.
    """
    async with with_repo(url, ref) as repo_path:
        match await read_files(repo_path, paths):
            case Success(results):
                pass

        # Format output
        output_parts = []
        for r in results:
            if r.error:
                output_parts.append(f"── {r.path} ──\n[{r.error}]")
            else:
                output_parts.append(f"── {r.path} ──\n{r.content}")

        return "\n\n".join(output_parts)


@mcp.tool
async def grep(
    url: Annotated[str, REPO_URL_FIELD],
    pattern: Annotated[str, Field(description="Regex pattern to search for")],
    ref: Annotated[str | None, REPO_REF_FIELD] = None,
    glob: Annotated[str | None, Field(description="Limit search to files matching this glob")] = None,
    context_lines: Annotated[int, Field(description="Lines of context around matches", ge=0, le=10)] = 3,
) -> str:
    """Search for a pattern in an external GitHub repository's files.

    Use this to find specific code patterns, function definitions, or usages in
    repos you don't have locally. Scout clones the repo to a temp directory.
    Specify a ref (branch/tag/commit) to search a specific version, or omit it
    to use the repo's default branch (usually main/master).

    Returns matching lines with file paths, line numbers, and context.
    Uses ripgrep (fast, respects .gitignore).

    Examples:
        - pattern="def.*async" - find async function definitions
        - pattern="TODO|FIXME" - find todos
        - pattern="import.*fastapi", glob="**/*.py" - find FastAPI imports
    """
    async with with_repo(url, ref) as path:
        match await grep_files(path, pattern, glob, context_lines):
            case Success(result):
                return result.output
            case NoResults():
                return f"No matches for '{pattern}'"


@mcp.tool
async def tree(
    url: Annotated[str, REPO_URL_FIELD],
    ref: Annotated[str | None, REPO_REF_FIELD] = None,
    path: Annotated[str, REPO_PATH_FIELD] = "",
    max_depth: Annotated[int, Field(description="Maximum depth to traverse", ge=1, le=10)] = 3,
) -> str:
    """Show directory structure of an external GitHub repository.

    Use this to understand project layout in repos you don't have locally.
    Scout clones the repo to a temp directory. Specify a ref (branch/tag/commit)
    to see a specific version, or omit it to use the repo's default branch
    (usually main/master).

    Returns a tree view of files and directories. Uses lstr (fast, respects
    .gitignore).

    Example output:
        src/
        ├── __init__.py
        ├── core.py
        └── utils/
            ├── __init__.py
            └── helpers.py
        tests/
        └── test_core.py
        README.md
    """
    async with with_repo(url, ref) as repo_path:
        match await build_tree(repo_path, path, max_depth):
            case Success(result):
                return result.output
            case NoResults():
                return "Empty directory"


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Entry point for `uv run scout` or `python -m sensei.scout`."""
    run_server(mcp, "scout", "Scout GitHub repo explorer MCP server")
