"""Tests for the markdown chunker."""

from sensei.tome.chunker import (
    chunk_markdown,
    reconstruct_content,
)


class TestHeadingParsing:
    """Tests for heading detection and parsing."""

    def test_no_headings_returns_flat(self):
        """Content without headings returns single root section."""
        content = "Just some plain text without any headings."
        result = chunk_markdown(content)
        assert result.heading is None
        assert result.content == content
        assert result.children == []

    def test_single_h2_heading(self):
        """Single heading creates one child section."""
        content = "## Getting Started\n\nSome content here."
        result = chunk_markdown(content)
        assert len(result.children) == 1
        assert result.children[0].heading == "Getting Started"
        assert result.children[0].level == 2

    def test_multiple_h2_headings(self):
        """Multiple same-level headings create sibling sections."""
        content = """## First Section

Content for first.

## Second Section

Content for second.
"""
        result = chunk_markdown(content)
        assert len(result.children) == 2
        assert result.children[0].heading == "First Section"
        assert result.children[1].heading == "Second Section"

    def test_mixed_level_headings_builds_tree(self):
        """Mixed heading levels build proper tree structure."""
        content = """## Main Section

Introduction.

### Subsection

Details here.

## Another Main

More content.
"""
        result = chunk_markdown(content)
        # Two h2 sections at top level
        assert len(result.children) == 2
        assert result.children[0].heading == "Main Section"
        assert result.children[1].heading == "Another Main"
        # First h2 has one h3 child
        assert len(result.children[0].children) == 1
        assert result.children[0].children[0].heading == "Subsection"


class TestChunkMarkdown:
    """Tests for the main chunking function."""

    def test_small_content_preserves_structure(self):
        """Small content should still preserve heading structure."""
        content = "# Small Document\n\nThis is small."
        result = chunk_markdown(content)

        # Root section with child for the h1
        assert result.heading is None
        assert result.level == 0
        assert result.content == ""  # No intro before first heading
        assert len(result.children) == 1
        assert result.children[0].heading == "Small Document"
        assert result.children[0].level == 1

    def test_nested_headings_build_full_tree(self):
        """Nested headings build complete tree structure."""
        h3_1 = "### Sub One\n\n" + "word " * 10
        h3_2 = "### Sub Two\n\n" + "word " * 10
        h2_section = "## Big Section\n\nIntro.\n\n" + h3_1 + "\n\n" + h3_2

        result = chunk_markdown(h2_section)

        # Should have one h2 child that contains h3 children
        assert len(result.children) == 1
        h2_child = result.children[0]
        assert h2_child.heading == "Big Section"
        assert len(h2_child.children) == 2
        assert h2_child.children[0].heading == "Sub One"
        assert h2_child.children[1].heading == "Sub Two"

    def test_position_ordering_is_correct(self):
        """Verify sections are created in document order."""
        content = """## First

First content.

## Second

Second content.

## Third

Third content.
"""
        result = chunk_markdown(content)

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
        result = chunk_markdown(content)
        assert len(result.children) == 1
        assert result.children[0].heading == "Title Here"
        assert result.children[0].level == 1

    def test_setext_h2_heading(self):
        """Setext H2 (underlined with ---) should be recognized."""
        content = """Subtitle Here
-------------

Some content.
"""
        result = chunk_markdown(content)
        assert len(result.children) == 1
        assert result.children[0].heading == "Subtitle Here"
        assert result.children[0].level == 2

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
        result = chunk_markdown(content)
        # H1 (setext) is top level with h2 children
        assert len(result.children) == 1
        assert result.children[0].heading == "Main Title"
        assert result.children[0].level == 1
        # H2s are children of the h1
        assert len(result.children[0].children) == 2


class TestRoundTrip:
    """Tests for round-trip reconstruction accuracy."""

    def test_small_content_round_trip(self):
        """Small content should round-trip exactly."""
        content = "# Small Document\n\nThis is small."
        result = chunk_markdown(content)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_no_headings_round_trip(self):
        """Content without headings should round-trip."""
        content = "Just plain text without headings."
        result = chunk_markdown(content)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_simple_split_round_trip(self):
        """Content split at top level should round-trip."""
        content = """## First

First content.

## Second

Second content."""
        result = chunk_markdown(content)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_nested_split_round_trip(self):
        """Nested headings should round-trip."""
        content = """## Main Section

Introduction.

### Sub One

Sub one content.

### Sub Two

Sub two content."""
        result = chunk_markdown(content)
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
        result = chunk_markdown(content)
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
        result = chunk_markdown(content)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_preserves_blank_lines(self):
        """Blank lines between sections should be preserved."""
        content = """## First

Content here.

## Second

More content."""
        result = chunk_markdown(content)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_preserves_trailing_content(self):
        """Content at end of sections should be preserved."""
        content = """## Section One

Line one.

## Section Two

Line two."""
        result = chunk_markdown(content)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content

    def test_intro_before_first_heading(self):
        """Intro content before first heading should be preserved."""
        content = """This is intro content.

# First Heading

Heading content."""
        result = chunk_markdown(content)
        reconstructed = reconstruct_content(result)
        assert reconstructed == content
