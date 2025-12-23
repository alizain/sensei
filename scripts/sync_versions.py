#!/usr/bin/env python3
"""Sync version from pyproject.toml to other files.

This script reads the version from pyproject.toml and updates:
- README.md version badge
- packages/sensei-claude-code/.claude-plugin/plugin.json
- package.json (root monorepo)

Run manually or via pre-commit hook.
"""

import json
import re
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_installed_version
from pathlib import Path

from sensei.types import BrokenInvariant

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"
PLUGIN_JSON = ROOT / "packages" / "sensei-claude-code" / ".claude-plugin" / "plugin.json"
PACKAGE_JSON = ROOT / "package.json"
OPENCODE_PACKAGE_JSON = ROOT / "packages" / "sensei-opencode" / "package.json"

PACKAGE_NAME = "sensei-ai"

# Semver pattern: X.Y.Z with optional pre-release/build metadata
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(-[\w.]+)?(\+[\w.]+)?$")

# README badge pattern
BADGE_PATTERN = re.compile(
    r"(\[!\[Version\]\(https://img\.shields\.io/badge/version-)"
    r"([^-]+)"
    r"(-.+\.svg\)\])"
)


# =============================================================================
# Core (pure functions, no I/O)
# =============================================================================


def validate_version(version: str) -> str:
    """Validate version string format. Returns version or raises ValueError."""
    if not version:
        raise ValueError("Version cannot be empty")
    if not VERSION_PATTERN.match(version):
        raise ValueError(f"Invalid version format: {version}")
    return version


def get_version() -> str:
    """Get version from installed package metadata."""
    try:
        version = get_installed_version(PACKAGE_NAME)
    except PackageNotFoundError:
        raise ValueError(f"Package '{PACKAGE_NAME}' not installed. Run 'uv sync' first.")
    return validate_version(version)


def transform_readme(content: str, version: str) -> tuple[str, bool]:
    """Transform README content with new version.

    Returns:
        (new_content, badge_found) - new_content may equal content if version unchanged
    """
    match = BADGE_PATTERN.search(content)
    if not match:
        return content, False  # Badge not found

    current_version = match.group(2)
    if current_version == version:
        return content, True  # Badge found, version unchanged

    new_content = BADGE_PATTERN.sub(rf"\g<1>{version}\g<3>", content)
    return new_content, True


def transform_plugin_json(data: dict, version: str) -> tuple[dict, bool]:
    """Transform plugin.json data with new version.

    Returns:
        (new_data, changed) - new_data may equal data if version unchanged
    """
    if data.get("version") == version:
        return data, False

    new_data = {**data, "version": version}
    return new_data, True


def serialize_plugin_json(data: dict) -> str:
    """Serialize plugin.json with consistent formatting (tabs, trailing newline)."""
    return json.dumps(data, indent="\t") + "\n"


# =============================================================================
# Edge (I/O functions)
# =============================================================================


def read_file(path: Path) -> str:
    """Read file content. Raises BrokenInvariant if missing."""
    try:
        return path.read_text()
    except FileNotFoundError:
        raise BrokenInvariant(f"Required file not found: {path}")


def write_file(path: Path, content: str) -> None:
    """Write content to file."""
    path.write_text(content)


def stage_file(path: Path) -> None:
    """Stage a file for git commit."""
    subprocess.run(["git", "add", str(path)], check=True, cwd=ROOT)


# =============================================================================
# Orchestration
# =============================================================================


def sync_readme(version: str) -> str | None:
    """Sync README badge. Returns status message or None if unchanged."""
    content = read_file(README)
    new_content, badge_found = transform_readme(content, version)

    if not badge_found:
        raise BrokenInvariant("Version badge not found in README.md")

    if new_content != content:
        write_file(README, new_content)
        stage_file(README)
        return "README.md"

    return None


def sync_plugin_json(version: str) -> str | None:
    """Sync plugin.json. Returns status message or None if unchanged."""
    content = read_file(PLUGIN_JSON)
    data = json.loads(content)
    new_data, changed = transform_plugin_json(data, version)

    if changed:
        write_file(PLUGIN_JSON, serialize_plugin_json(new_data))
        stage_file(PLUGIN_JSON)
        return "plugin.json"

    return None


def sync_package_json(version: str) -> str | None:
    """Sync package.json. Returns status message or None if unchanged."""
    content = read_file(PACKAGE_JSON)
    data = json.loads(content)
    new_data, changed = transform_plugin_json(data, version)

    if changed:
        write_file(PACKAGE_JSON, serialize_plugin_json(new_data))
        stage_file(PACKAGE_JSON)
        return "package.json"

    return None


def sync_opencode_package_json(version: str) -> str | None:
    """Sync @sensei-ai/opencode package.json. Returns status message or None if unchanged."""
    content = read_file(OPENCODE_PACKAGE_JSON)
    data = json.loads(content)
    new_data, changed = transform_plugin_json(data, version)

    if changed:
        write_file(OPENCODE_PACKAGE_JSON, serialize_plugin_json(new_data))
        stage_file(OPENCODE_PACKAGE_JSON)
        return "packages/sensei-opencode/package.json"

    return None


def main() -> int:
    """Main entry point."""
    try:
        version = get_version()
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except BrokenInvariant as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Version from package metadata: {version}")

    updated = []

    try:
        for sync_fn in [sync_readme, sync_plugin_json, sync_package_json, sync_opencode_package_json]:
            result = sync_fn(version)
            if result is not None:
                updated.append(result)
    except BrokenInvariant as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if updated:
        print(f"Updated and staged: {', '.join(updated)}")
    else:
        print("All versions already in sync")

    return 0


if __name__ == "__main__":
    sys.exit(main())
