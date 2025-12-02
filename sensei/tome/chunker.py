"""Markdown chunker that preserves heading structure.

Parses markdown documents into a tree structure based on headings.
PostgreSQL's tsvector limit is the constraint - if content is too large,
the database will error and the crawler will skip that document.

Algorithm (two-phase, no recursion for main tree building):
1. Parse all headings once using markdown-it-py
2. Build tree iteratively using stack-based approach
3. Convert to SectionData

This avoids:
- Re-parsing markdown at each nesting level
- Deep recursion (Python has no tail-call optimization)
- Temporary field hacks for passing position info
"""

import logging
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

from sensei.types import SectionData

logger = logging.getLogger(__name__)

# Singleton markdown parser
_md = MarkdownIt()


# =============================================================================
# Internal data structures for tree building
# =============================================================================


@dataclass
class _HeadingInfo:
    """Parsed heading with position info."""

    text: str
    level: int
    start_line: int  # 0-indexed


@dataclass
class _TreeNode:
    """Intermediate node for tree construction.

    Tracks line positions for content extraction. This is the internal
    representation - converted to SectionData at the end.
    """

    heading: str | None
    level: int
    start_line: int  # Where this section starts (inclusive)
    content_end: int  # Where intro content ends (exclusive) - may be updated when children added
    children: list["_TreeNode"] = field(default_factory=list)


# =============================================================================
# Public API
# =============================================================================


def chunk_markdown(content: str) -> SectionData:
    """Build heading tree from markdown content.

    Args:
        content: Markdown content to chunk

    Returns:
        Root SectionData with children representing the document structure
    """
    lines = content.split("\n")
    headings = _parse_headings(content)

    if not headings:
        # No headings - single root section
        return SectionData(heading=None, level=0, content=content, children=[])

    # Build tree from headings (single pass, iterative)
    tree = _build_tree(lines, headings)

    # Convert to SectionData
    return _to_section_data(tree, lines)


def reconstruct_content(section: SectionData) -> str:
    """Reconstruct markdown from section tree.

    Iterative DFS using explicit stack. This is the inverse of chunk_markdown.
    """
    if not section.children:
        return section.content

    logger.info("Processing section: %s", section)

    parts: list[str] = []
    stack: list[SectionData] = [section]

    while stack:
        node = stack.pop()
        logger.info("Processing node: %s", node)

        if node.content:
            parts.append(node.content)

        # Push children in reverse order (so first child processed first)
        stack.extend(reversed(node.children))

    return "\n".join(parts)


# =============================================================================
# Phase 1: Parse headings (single pass)
# =============================================================================


def _parse_headings(content: str) -> list[_HeadingInfo]:
    """Extract all headings from markdown with position info.

    Single pass through markdown-it tokens. Handles both ATX (###)
    and Setext (underline) style headings.
    """
    tokens = _md.parse(content)
    headings: list[_HeadingInfo] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "heading_open" and token.map is not None:
            level = int(token.tag[1])  # h1 -> 1, h2 -> 2, etc.
            start_line = token.map[0]

            # Next token is 'inline' containing the heading text
            text = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                inline = tokens[i + 1]
                if inline.children:
                    text = "".join(c.content for c in inline.children if c.content)
                elif inline.content:
                    text = inline.content

            headings.append(_HeadingInfo(text=text, level=level, start_line=start_line))

        i += 1

    return headings


# =============================================================================
# Phase 2: Build tree (iterative, stack-based)
# =============================================================================


def _build_tree(lines: list[str], headings: list[_HeadingInfo]) -> _TreeNode:
    """Build tree from headings using iterative stack-based approach.

    Single O(n) pass through headings. No recursion.

    The stack tracks the path from root to current position. When we
    encounter a heading, we pop until we find a node with lower level
    (the parent), then add the new node as a child.
    """
    total_lines = len(lines)

    # Root node - intro is content before first heading
    root = _TreeNode(
        heading=None,
        level=0,
        start_line=0,
        content_end=headings[0].start_line,  # Intro ends where first heading starts
    )

    # Stack tracks path from root to current node
    stack: list[_TreeNode] = [root]

    for i, heading in enumerate(headings):
        # Content for this heading ends at next heading or EOF
        content_end = headings[i + 1].start_line if i + 1 < len(headings) else total_lines

        node = _TreeNode(
            heading=heading.text,
            level=heading.level,
            start_line=heading.start_line,
            content_end=content_end,
        )

        # Pop until we find parent (level < this heading)
        while stack[-1].level >= heading.level:
            stack.pop()

        # Add to parent
        parent = stack[-1]
        if not parent.children:
            # First child - parent's intro content ends here
            parent.content_end = heading.start_line
        parent.children.append(node)

        stack.append(node)

    return root


# =============================================================================
# Phase 3: Convert to SectionData
# =============================================================================


def _to_section_data(tree: _TreeNode, lines: list[str]) -> SectionData:
    """Convert TreeNode to SectionData.

    Uses bounded recursion (max depth = 6 for h1-h6), which is safe.
    The heavy lifting (tree building) is done iteratively in _build_tree.
    """
    content = "\n".join(lines[tree.start_line : tree.content_end])

    if not tree.children:
        # Leaf node
        return SectionData(
            heading=tree.heading,
            level=tree.level,
            content=content,
            children=[],
        )

    # Branch node - convert children (recursion bounded by heading depth, max 6)
    children = [_to_section_data(child, lines) for child in tree.children]

    return SectionData(
        heading=tree.heading,
        level=tree.level,
        content=content,
        children=children,
    )
