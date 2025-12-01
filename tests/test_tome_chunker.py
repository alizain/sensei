"""Tests for the adaptive recursive markdown chunker."""

import pytest

from sensei.tome.chunker import (
    chunk_markdown,
    count_tokens,
    reconstruct_content,
    _split_by_top_level_headings,
)
from sensei.types import BrokenInvariant


class TestCountTokens:
    """Tests for token counting."""

    def test_count_empty(self):
        assert count_tokens("") == 0

    def test_count_single_word(self):
        assert count_tokens("hello") == 1

    def test_count_multiple_words(self):
        assert count_tokens("hello world how are you") == 5

    def test_count_with_newlines(self):
        assert count_tokens("hello\nworld\ntest") == 3


class TestSplitByTopLevelHeadings:
    """Tests for splitting markdown by headings."""

    def test_no_headings_returns_empty(self):
        content = "Just some plain text without any headings."
        result = _split_by_top_level_headings(content.split("\n"))
        assert result == []

    def test_single_h2_heading(self):
        content = "## Getting Started\n\nSome content here."
        result = _split_by_top_level_headings(content.split("\n"))
        assert len(result) == 1
        assert result[0].heading == "Getting Started"
        assert result[0].level == 2

    def test_multiple_h2_headings(self):
        content = """## First Section

Content for first.

## Second Section

Content for second.
"""
        result = _split_by_top_level_headings(content.split("\n"))
        assert len(result) == 2
        assert result[0].heading == "First Section"
        assert result[1].heading == "Second Section"

    def test_mixed_level_headings_splits_at_top_level(self):
        content = """## Main Section

Introduction.

### Subsection

Details here.

## Another Main

More content.
"""
        result = _split_by_top_level_headings(content.split("\n"))
        # Should split at h2 level (top level in this content)
        assert len(result) == 2
        assert result[0].heading == "Main Section"
        assert result[1].heading == "Another Main"


class TestChunkMarkdown:
    """Tests for the main chunking function."""

    def test_small_content_returns_single_section(self):
        """Content under max_tokens should return as single root section."""
        content = "# Small Document\n\nThis is small."
        result = chunk_markdown(content, max_tokens=1000)

        # Root section with content, no children
        assert result.heading is None
        assert result.level == 0
        assert result.content == content
        assert result.children == []

    def test_large_content_splits_by_headings(self):
        """Content over max_tokens should split at heading boundaries."""
        # Create content with two small sections that individually fit
        section1 = "## First\n\nword " * 10  # ~20 tokens
        section2 = "## Second\n\nword " * 10  # ~20 tokens
        content = section1 + "\n\n" + section2

        # Set max_tokens so total exceeds but each section fits
        result = chunk_markdown(content, max_tokens=30)

        # Root should have children (split at top level)
        assert result.heading is None
        assert result.level == 0
        assert len(result.children) == 2
        assert result.children[0].heading == "First"
        assert result.children[1].heading == "Second"

    def test_recursive_chunking_with_nested_headings(self):
        """Test that chunking recurses into subsections when needed."""
        # Create a large h2 section with h3 subsections (each h3 is small)
        h3_1 = "### Sub One\n\n" + "word " * 10  # ~12 tokens
        h3_2 = "### Sub Two\n\n" + "word " * 10  # ~12 tokens
        h2_section = "## Big Section\n\nIntro.\n\n" + h3_1 + "\n\n" + h3_2

        # Set max_tokens so h2 exceeds but h3s fit
        result = chunk_markdown(h2_section, max_tokens=20)

        # Should have one h2 child that contains h3 children
        assert len(result.children) == 1
        h2_child = result.children[0]
        assert h2_child.heading == "Big Section"
        assert len(h2_child.children) == 2
        assert h2_child.children[0].heading == "Sub One"
        assert h2_child.children[1].heading == "Sub Two"

    def test_raises_on_large_content_without_headings(self):
        """Content too large with no headings should raise BrokenInvariant."""
        # Large content with no headings
        content = "word " * 10000

        with pytest.raises(BrokenInvariant) as excinfo:
            chunk_markdown(content, max_tokens=100)

        assert "no heading boundaries" in str(excinfo.value).lower()

    def test_position_ordering_is_correct(self):
        """Verify sections are created in document order."""
        content = """## First

First content.

## Second

Second content.

## Third

Third content.
"""
        # Set max_tokens high enough that we need to split at top level
        # but each individual section fits
        result = chunk_markdown(content, max_tokens=10)

        # Extract children headings in order
        headings = [c.heading for c in result.children]
        assert headings == ["First", "Second", "Third"]


class TestSetextHeadings:
    """Tests for setext-style headings (underlined with === or ---)."""

    def test_setext_h1_heading(self):
        """Setext H1 (underlined with ===) should be recognized."""
        content = """Title Here
==========

Some content.
"""
        result = _split_by_top_level_headings(content.split("\n"))
        assert len(result) == 1
        assert result[0].heading == "Title Here"
        assert result[0].level == 1

    def test_setext_h2_heading(self):
        """Setext H2 (underlined with ---) should be recognized."""
        content = """Subtitle Here
-------------

Some content.
"""
        result = _split_by_top_level_headings(content.split("\n"))
        assert len(result) == 1
        assert result[0].heading == "Subtitle Here"
        assert result[0].level == 2

    def test_mixed_atx_and_setext(self):
        """Both ATX and Setext headings should work together."""
        content = """Main Title
==========

Introduction.

## ATX Section

ATX content.

Another Section
---------------

More content.
"""
        result = _split_by_top_level_headings(content.split("\n"))
        # H1 (setext) is top level, so only one section at that level
        assert len(result) == 1
        assert result[0].heading == "Main Title"
        assert result[0].level == 1


class TestRoundTrip:
    """Tests for round-trip reconstruction accuracy."""

    def test_small_content_round_trip(self):
        """Small content (not chunked) should round-trip exactly."""
        content = "# Small Document\n\nThis is small."
        result = chunk_markdown(content, max_tokens=1000)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_simple_split_round_trip(self):
        """Content split once at top level should round-trip."""
        content = """## First

First content.

## Second

Second content."""
        result = chunk_markdown(content, max_tokens=5)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_nested_split_round_trip(self):
        """Recursively chunked content should round-trip."""
        content = """## Main Section

Introduction.

### Sub One

Sub one content.

### Sub Two

Sub two content."""
        result = chunk_markdown(content, max_tokens=8)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_complex_document_round_trip(self):
        """Complex multi-level document should round-trip."""
        content = """# Document Title

Overview paragraph.

## First Section

First intro.

### First Subsection

First sub content.

### Second Subsection

Second sub content.

## Second Section

Second section content.

### Another Sub

More content here."""
        result = chunk_markdown(content, max_tokens=10)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_setext_headings_round_trip(self):
        """Setext-style headings should round-trip."""
        content = """Main Title
==========

Introduction.

Sub Section
-----------

Sub content."""
        result = chunk_markdown(content, max_tokens=5)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_preserves_blank_lines(self):
        """Blank lines between sections should be preserved."""
        content = """## First

Content here.

## Second

More content."""
        result = chunk_markdown(content, max_tokens=5)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_preserves_trailing_content(self):
        """Content at end of sections should be preserved."""
        content = """## Section One

Line one.

## Section Two

Line two."""
        result = chunk_markdown(content, max_tokens=5)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content
