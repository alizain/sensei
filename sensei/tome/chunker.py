"""Adaptive recursive markdown chunker.

Splits markdown documents by headings to ensure each section fits within
PostgreSQL's tsvector size limit (~1MB). The algorithm:

1. If content fits within max_tokens, return as single section
2. If too large, split by top-level headings in the content
3. Recursively chunk any sections that are still too large
4. Raise error if content exceeds limit with no heading boundaries

Uses markdown-it-py for parsing, which provides:
- Line position tracking for accurate splitting
- Both ATX (###) and Setext (underline) heading support
"""

from dataclasses import dataclass

from markdown_it import MarkdownIt

from sensei.types import BrokenInvariant, SectionData

# Singleton markdown parser
_md = MarkdownIt()

# Default max tokens - conservative estimate to stay well under 1MB tsvector limit
# Using ~4 chars per token average, 8000 tokens ≈ 32KB which leaves plenty of margin
DEFAULT_MAX_TOKENS = 8000


@dataclass
class _HeadingInfo:
	"""Internal representation of a heading with position info."""

	text: str
	level: int
	start_line: int  # 0-indexed, inclusive
	end_line: int  # 0-indexed, exclusive (line after heading)


def count_tokens(content: str) -> int:
	"""Estimate token count using simple word-based heuristic.

	Uses whitespace splitting as a rough approximation. This is intentionally
	simple - if we need exact counts, we can add tiktoken later.

	Args:
	    content: Text to count tokens for

	Returns:
	    Estimated token count
	"""
	# Split on whitespace, count words. Roughly 1.3 tokens per word on average
	# but we use 1:1 for simplicity since we have large margin in max_tokens
	return len(content.split())


def chunk_markdown(content: str, max_tokens: int = DEFAULT_MAX_TOKENS) -> SectionData:
	"""Chunk markdown content into sections by headings.

	The algorithm adaptively splits content at heading boundaries when it
	exceeds max_tokens. It finds the top-level headings in the current content
	and splits there, recursively processing any sections that are still too large.

	Args:
	    content: Markdown content to chunk
	    max_tokens: Maximum tokens per section (default 8000)

	Returns:
	    Root SectionData with children representing the document structure

	Raises:
	    BrokenInvariant: If content exceeds limit with no heading boundaries
	"""
	if count_tokens(content) <= max_tokens:
		# Content fits - return as single root section
		return SectionData(heading=None, level=0, content=content, children=[])

	# Too large - split by headings
	lines = content.split("\n")
	sections = _split_by_top_level_headings(lines)

	if not sections:
		# No headings found but content too large - this is an error condition
		raise BrokenInvariant(
			f"Content exceeds {max_tokens} tokens with no heading boundaries. "
			f"Content length: {count_tokens(content)} tokens"
		)

	# Recursively chunk any sections that are still too large
	root_children: list[SectionData] = []
	for section in sections:
		if count_tokens(section.content) <= max_tokens:
			root_children.append(section)
		else:
			# Section too large - recursively chunk it
			chunked = _chunk_section(section, max_tokens)
			root_children.append(chunked)

	# Return root section containing all children
	return SectionData(heading=None, level=0, content="", children=root_children)


def _chunk_section(section: SectionData, max_tokens: int) -> SectionData:
	"""Recursively chunk a section that's too large.

	Args:
	    section: Section to chunk
	    max_tokens: Maximum tokens per section

	Returns:
	    Section with children chunked if needed

	Raises:
	    BrokenInvariant: If section exceeds limit with no heading boundaries
	"""
	if count_tokens(section.content) <= max_tokens:
		return section

	# Parse the section content to find sub-headings DEEPER than current level
	lines = section.content.split("\n")
	sub_sections = _split_by_subheadings(lines, section.level)

	if not sub_sections:
		# No sub-headings but content too large
		raise BrokenInvariant(
			f"Section '{section.heading}' exceeds {max_tokens} tokens with no "
			f"heading boundaries. Content length: {count_tokens(section.content)} tokens"
		)

	# Recursively chunk sub-sections
	chunked_children: list[SectionData] = []
	for sub_section in sub_sections:
		if count_tokens(sub_section.content) <= max_tokens:
			chunked_children.append(sub_section)
		else:
			chunked_children.append(_chunk_section(sub_section, max_tokens))

	# Return section with intro content and chunked children
	# The intro is content before the first sub-heading
	intro_content = _extract_intro(lines, sub_sections)
	return SectionData(
		heading=section.heading,
		level=section.level,
		content=intro_content,
		children=chunked_children,
	)


def _extract_intro(lines: list[str], sub_sections: list[SectionData]) -> str:
	"""Extract intro content before the first sub-heading.

	Args:
	    lines: Content split into lines
	    sub_sections: Parsed sub-sections (with _start_line attribute)

	Returns:
	    Content before the first heading, or empty string if none
	"""
	if not sub_sections:
		return "\n".join(lines)

	# Get the start line of the first sub-section
	first_section = sub_sections[0]
	# We store start_line in a temporary attribute during splitting
	start_line = getattr(first_section, "_start_line", 0)

	if start_line == 0:
		return ""

	# Don't strip - preserve trailing blank lines for accurate round-trip
	return "\n".join(lines[:start_line])


def _split_by_top_level_headings(lines: list[str]) -> list[SectionData]:
	"""Split content by its top-level headings.

	Finds the minimum heading level in the content and splits at those boundaries.
	For example, if content has h2 and h3 headings, splits only at h2 boundaries.

	Args:
	    lines: Content split into lines

	Returns:
	    List of SectionData for each top-level section
	"""
	return _split_by_headings_at_level(lines, min_level=None)


def _split_by_subheadings(lines: list[str], parent_level: int) -> list[SectionData]:
	"""Split content by headings deeper than the parent level.

	Used when recursively chunking - we only want to split at sub-headings,
	not at the same level as the parent.

	Args:
	    lines: Content split into lines
	    parent_level: Level of the parent section (only split at levels > this)

	Returns:
	    List of SectionData for each sub-section
	"""
	return _split_by_headings_at_level(lines, min_level=parent_level + 1)


def _split_by_headings_at_level(
	lines: list[str],
	min_level: int | None = None,
) -> list[SectionData]:
	"""Split content by headings at or above a minimum level.

	Args:
	    lines: Content split into lines
	    min_level: Minimum heading level to consider (None = use top level found)

	Returns:
	    List of SectionData for each section
	"""
	content = "\n".join(lines)
	headings = _find_headings(content)

	if not headings:
		return []

	# Filter by minimum level if specified
	if min_level is not None:
		headings = [h for h in headings if h.level >= min_level]
		if not headings:
			return []

	# Find the minimum (top) level among remaining headings
	top_level = min(h.level for h in headings)

	# Filter to only the top level (among filtered headings)
	top_headings = [h for h in headings if h.level == top_level]

	if not top_headings:
		return []

	# Split content at heading boundaries
	sections: list[SectionData] = []

	for i, heading in enumerate(top_headings):
		start_line = heading.start_line

		# Find end of this section (start of next top-level heading or end of content)
		if i + 1 < len(top_headings):
			end_line = top_headings[i + 1].start_line
		else:
			end_line = len(lines)

		# Extract section content (including the heading line)
		# Don't strip - preserve trailing blank lines for accurate round-trip
		section_content = "\n".join(lines[start_line:end_line])

		section = SectionData(
			heading=heading.text,
			level=heading.level,
			content=section_content,
			children=[],
		)
		# Store start_line for intro extraction (temporary attribute)
		section._start_line = start_line  # type: ignore[attr-defined]
		sections.append(section)

	return sections


def _find_headings(content: str) -> list[_HeadingInfo]:
	"""Extract all headings from markdown content with position info.

	Handles both ATX (###) and Setext (underline) style headings.

	Args:
	    content: Markdown content to parse

	Returns:
	    List of HeadingInfo with text, level, and line positions
	"""
	tokens = _md.parse(content)
	headings: list[_HeadingInfo] = []

	i = 0
	while i < len(tokens):
		token = tokens[i]

		if token.type == "heading_open" and token.map is not None:
			# Extract level from tag (h1 -> 1, h2 -> 2, etc.)
			level = int(token.tag[1])
			start_line = token.map[0]
			end_line = token.map[1]

			# Next token is 'inline' containing the heading text
			text = ""
			if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
				inline_token = tokens[i + 1]
				# Get text from inline children
				if inline_token.children:
					text = "".join(child.content for child in inline_token.children if child.content)
				elif inline_token.content:
					text = inline_token.content

			headings.append(
				_HeadingInfo(
					text=text,
					level=level,
					start_line=start_line,
					end_line=end_line,
				)
			)

		i += 1

	return headings


def reconstruct_content(section: SectionData) -> str:
	"""Reconstruct the original markdown content from a chunked SectionData tree.

	This is the inverse of chunk_markdown - it reassembles the document from
	the section tree. Used for testing round-trip accuracy.

	Args:
	    section: Root SectionData (or any section node)

	Returns:
	    Reconstructed markdown content
	"""
	if not section.children:
		# Leaf node - return content directly
		return section.content

	# Has children - combine intro content with children
	parts: list[str] = []

	# Add intro content if present
	if section.content:
		parts.append(section.content)

	# Recursively reconstruct children
	for child in section.children:
		parts.append(reconstruct_content(child))

	return "\n".join(parts)
