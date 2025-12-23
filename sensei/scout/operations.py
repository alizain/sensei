"""Core operations for repository exploration.

Pure functions that operate on local paths. No MCP concerns, no formatting.
These are the building blocks that server.py composes.

All file discovery uses ripgrep/lstr which respect .gitignore by default.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

from sensei.types import BrokenInvariant, NoResults, Success, ToolError, TransientError

# ─────────────────────────────────────────────────────────────────────────────
# Dependency Verification
# ─────────────────────────────────────────────────────────────────────────────

_REQUIRED_TOOLS = ["rg", "lstr", "git"]


def _verify_dependencies() -> None:
    """Check required CLI tools are installed. Called at module load."""
    missing = [tool for tool in _REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        raise BrokenInvariant(f"Scout requires these tools to be installed: {', '.join(missing)}")


_verify_dependencies()


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess Helper
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CommandResult:
    """Result of running a shell command."""

    stdout: bytes
    stderr: bytes
    returncode: int


async def run_command(cmd: list[str]) -> CommandResult:
    """Run a command with timeout, returning stdout/stderr/returncode.

    Args:
        cmd: Command and arguments as a list

    Returns:
        CommandResult with stdout, stderr, and returncode

    Raises:
        TransientError: If command times out after 30s
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        async with asyncio.timeout(30):
            stdout, stderr = await proc.communicate()
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise TransientError(f"Command timed out after 30s: {cmd[0]}")

    return CommandResult(stdout=stdout, stderr=stderr, returncode=proc.returncode)


# ─────────────────────────────────────────────────────────────────────────────
# Glob (using ripgrep for gitignore support)
# ─────────────────────────────────────────────────────────────────────────────


async def glob_files(root: Path, pattern: str) -> Success[list[Path]]:
    """Find files matching a glob pattern using ripgrep.

    Uses ripgrep's --files mode which respects .gitignore by default.

    Args:
        root: Repository root path
        pattern: Glob pattern (e.g., "**/*.py")

    Returns:
        Success with list of matching file paths (absolute), sorted alphabetically

    Raises:
        ToolError: If ripgrep encounters an error (bad pattern, etc.)
    """
    cmd = [
        "rg",
        "--files",
        "--glob",
        pattern,
        "--color=never",
        str(root),
    ]

    result = await run_command(cmd)

    if result.returncode == 2:  # rg error (bad pattern, etc.)
        raise ToolError(f"Glob failed: {result.stderr.decode().strip()}")

    if result.returncode == 1:  # No matches (valid result)
        return Success([])

    lines = result.stdout.decode(errors="replace").strip().split("\n")
    return Success(sorted(Path(line) for line in lines if line))


# ─────────────────────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FileContent:
    """Result of reading a file."""

    path: str  # Relative path
    content: str | None  # File content, or None if error
    error: str | None  # Error message, or None if success


async def read_files(root: Path, paths: list[str], max_size: int = 100_000) -> Success[list[FileContent]]:
    """Read one or more files from a repository.

    Args:
        root: Repository root path
        paths: List of relative file paths
        max_size: Maximum file size in bytes before truncation

    Returns:
        Success with list of FileContent results (individual files may have errors)
    """
    results = []

    for file_path in paths:
        full_path = root / file_path

        if not full_path.exists():
            results.append(FileContent(path=file_path, content=None, error="File not found"))
            continue

        if not full_path.is_file():
            results.append(FileContent(path=file_path, content=None, error="Not a file"))
            continue

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            if len(content) > max_size:
                content = content[:max_size] + f"\n\n[... truncated at {max_size // 1000}KB ...]"
            results.append(FileContent(path=file_path, content=content, error=None))
        except Exception as e:
            results.append(FileContent(path=file_path, content=None, error=str(e)))

    return Success(results)


# ─────────────────────────────────────────────────────────────────────────────
# Grep
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class GrepResult:
    """Result of a grep search."""

    output: str  # Ripgrep output with paths made relative
    match_count: int  # Approximate number of matches
    truncated: bool  # Whether output was truncated


async def grep_files(
    root: Path,
    pattern: str,
    glob: str | None = None,
    context_lines: int = 3,
    ignore_case: bool = True,
    max_output: int = 50_000,
) -> Success[GrepResult] | NoResults:
    """Search for a pattern in repository files using ripgrep.

    Ripgrep respects .gitignore by default, so no manual exclusions needed.

    Args:
        root: Repository root path
        pattern: Regex pattern to search for
        glob: Optional glob to limit search scope
        context_lines: Lines of context around matches
        max_output: Maximum output size in bytes

    Returns:
        Success with GrepResult, or NoResults if no matches found

    Raises:
        ToolError: If ripgrep encounters an error (bad pattern, etc.)
    """
    cmd = [
        "rg",
        "--line-number",
        f"--context={context_lines}",
        "--color=never",
        "--follow",
    ]

    if ignore_case:
        cmd.append("--ignore-case")

    if glob:
        cmd.extend(["--glob", glob])

    cmd.append(pattern)
    cmd.append(str(root))

    result = await run_command(cmd)

    if result.returncode == 1:  # No matches
        return NoResults()

    if result.returncode == 2:  # Error
        raise ToolError(f"Grep failed: {result.stderr.decode().strip()}")

    # Make paths relative
    output = result.stdout.decode(errors="replace")
    output = output.replace(str(root) + "/", "")

    # Count approximate matches (lines with file:line: pattern)
    match_count = output.count("\n")

    # Truncate if needed
    truncated = len(output) > max_output
    if truncated:
        output = output[:max_output] + f"\n\n[... truncated at {max_output // 1000}KB ...]"

    return Success(GrepResult(output=output, match_count=match_count, truncated=truncated))


# ─────────────────────────────────────────────────────────────────────────────
# Tree (using lstr)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class TreeResult:
    """Result of a tree operation."""

    output: str  # Tree output
    error: str | None  # Error message, or None if success


async def build_tree(
    root: Path,
    subpath: str = "",
    max_depth: int = 3,
) -> Success[TreeResult] | NoResults:
    """Build a tree view of directory structure using lstr.

    Args:
        root: Repository root path
        subpath: Subdirectory to start from (relative to root)
        max_depth: Maximum depth to traverse

    Returns:
        Success with TreeResult, or NoResults if directory is empty

    Raises:
        ToolError: If path not found, not a directory, or lstr fails
    """
    target = root / subpath if subpath else root

    if not target.exists():
        raise ToolError(f"Path '{subpath}' not found")

    if not target.is_dir():
        raise ToolError(f"Path '{subpath}' is not a directory")

    cmd = [
        "lstr",
        f"-L{max_depth}",
        "-g",  # Respect .gitignore
        "--color",
        "never",
        str(target),
    ]

    result = await run_command(cmd)

    if result.returncode != 0:
        raise ToolError(f"Tree failed: {result.stderr.decode().strip()}")

    output = result.stdout.decode(errors="replace")
    if not output.strip():
        return NoResults()

    return Success(TreeResult(output=output, error=None))


# ─────────────────────────────────────────────────────────────────────────────
# List Files (for repo_map)
# ─────────────────────────────────────────────────────────────────────────────


async def list_files(root: Path, subpath: str = "") -> Success[list[Path]]:
    """List all files in a directory using ripgrep.

    Uses ripgrep's --files mode which respects .gitignore by default.
    Aider's RepoMap will filter to files it can parse with tree-sitter.

    Args:
        root: Repository root path
        subpath: Subdirectory to list (relative to root), defaults to root

    Returns:
        Success with list of file paths (absolute)
    """
    target = root / subpath if subpath else root

    cmd = ["rg", "--files", "--color=never", str(target)]

    result = await run_command(cmd)

    if result.returncode == 2:  # rg error
        raise ToolError(f"List files failed: {result.stderr.decode().strip()}")

    if result.returncode == 1:  # No files found
        return Success([])

    lines = result.stdout.decode(errors="replace").strip().split("\n")
    return Success([Path(line) for line in lines if line])
