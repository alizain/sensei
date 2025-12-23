#!/usr/bin/env python3
"""Build script to generate Claude Code plugin files from prompts.py.

This script generates the skill from the composable prompts in
sensei/prompts.py. Run this before publishing the plugin.

Generates:
    - skills/documentation-research/SKILL.md

Usage:
    uv run python scripts/build_plugin.py
"""

from pathlib import Path

from sensei.prompts import build_prompt

# Paths relative to repo root
REPO_ROOT = Path(__file__).parent.parent
PLUGIN_DIR = REPO_ROOT / "packages" / "sensei-claude-code"

# Skill paths
SKILLS_DIR = PLUGIN_DIR / "skills" / "documentation-research"
SENSEI_SKILL_MD = SKILLS_DIR / "SKILL.md"

# YAML frontmatter for the skill
SKILL_FRONTMATTER = """\
---
name: documentation-research
description: >-
  Use when researching library documentation, framework APIs, best practices,
  or troubleshooting external code - teaches research methodology for finding
  the right answer, with the query tool for complex multi-source research
---

"""


def main() -> None:
    """Generate skill from prompts.py."""
    print("Building Claude Code plugin...\n")

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt("claude_code_skill")
    content = SKILL_FRONTMATTER + prompt
    SENSEI_SKILL_MD.write_text(content)

    print(f"Generated {SENSEI_SKILL_MD}")
    print(f"  - {len(prompt)} characters")
    print(f"  - {len(prompt.split())} words")

    print("\nDone!")


if __name__ == "__main__":
    main()
