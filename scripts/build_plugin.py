#!/usr/bin/env python3
"""Build script to generate Claude Code plugin files from prompts.py.

This script generates claude-code/agents/sensei.md from the composable
prompts in sensei/prompts.py. Run this before publishing the plugin.

Usage:
    uv run python scripts/build_plugin.py
"""

from pathlib import Path

from sensei.prompts import build_prompt

# Paths relative to repo root
REPO_ROOT = Path(__file__).parent.parent
PLUGIN_DIR = REPO_ROOT / "packages" / "marketplace" / "sensei"
AGENTS_DIR = PLUGIN_DIR / "agents"
SENSEI_MD = AGENTS_DIR / "sensei.md"

# YAML frontmatter for the sub-agent
FRONTMATTER = """\
---
name: sensei
description: >-
  Use when researching documentation, exploring external GitHub repositories,
  or understanding how code works in codebases outside the current workspace.
  Sensei uses Scout tools for external repos and Claude Code native tools for
  the current workspace.
---

"""


def main() -> None:
	"""Generate agents/sensei.md from prompts.py."""
	# Ensure agents directory exists
	AGENTS_DIR.mkdir(exist_ok=True)

	# Build the prompt for Claude Code context
	prompt = build_prompt("claude_code")

	# Write the agent file
	content = FRONTMATTER + prompt
	SENSEI_MD.write_text(content)

	print(f"Generated {SENSEI_MD}")
	print(f"  - {len(prompt)} characters")
	print(f"  - {len(prompt.split())} words")


if __name__ == "__main__":
	main()
