"""Tests for Tome parser functionality."""

from sensei.tome.crawler import is_markdown_content
from sensei.tome.parser import (
    extract_domain,
    extract_path,
    is_same_site,
    parse_llms_txt_links,
)
from sensei.types import Domain


def test_parse_llms_txt_links_extracts_markdown_links():
    content = """
# Example Docs

> Some description

## Getting Started
- [Quick Start](/docs/quickstart.md)
- [Installation](https://example.com/docs/install.md)

## API
- [Reference](/api/ref.md)
"""
    links = parse_llms_txt_links(content, "https://example.com/llms.txt")
    assert len(links) == 3
    assert "https://example.com/docs/quickstart.md" in links
    assert "https://example.com/docs/install.md" in links
    assert "https://example.com/api/ref.md" in links


def test_parse_llms_txt_links_ignores_anchor_only_links():
    content = "[Jump to section](#section)"
    links = parse_llms_txt_links(content, "https://example.com/llms.txt")
    assert len(links) == 0


def test_parse_llms_txt_links_extracts_reference_links():
    """Reference-style links should be resolved and extracted."""
    content = """
# Documentation

See the [Quick Start][quickstart] guide.
Also check [Installation][install] and [API Reference][quickstart].

[quickstart]: /docs/quickstart.md
[install]: https://example.com/docs/install.md "Installation Guide"
"""
    links = parse_llms_txt_links(content, "https://example.com/llms.txt")
    assert len(links) == 2  # quickstart appears twice but should be deduplicated
    assert "https://example.com/docs/quickstart.md" in links
    assert "https://example.com/docs/install.md" in links


def test_parse_llms_txt_links_extracts_autolinks():
    """Autolinks <url> should be extracted."""
    content = """
# Contact

Website: <https://example.com/contact>
API: <https://api.example.com/v1>
"""
    links = parse_llms_txt_links(content, "https://example.com/llms.txt")
    assert len(links) == 2
    assert "https://example.com/contact" in links
    assert "https://api.example.com/v1" in links


def test_parse_llms_txt_links_ignores_mailto_autolinks():
    """Mailto autolinks should be ignored."""
    content = """
Contact us at <admin@example.com>
Or visit <https://example.com/support>
"""
    links = parse_llms_txt_links(content, "https://example.com/llms.txt")
    assert len(links) == 1
    assert "https://example.com/support" in links


def test_parse_llms_txt_links_mixed_formats():
    """All link formats should work together."""
    content = """
# Full Documentation

## Inline Links
- [Getting Started](/docs/start.md)
- [Tutorial](https://example.com/tutorial)

## Reference Links
Check the [API docs][api] for details.

## Autolinks
Quick access: <https://example.com/quick>

[api]: /docs/api.md "API Documentation"
"""
    links = parse_llms_txt_links(content, "https://example.com/llms.txt")
    assert len(links) == 4
    assert "https://example.com/docs/start.md" in links
    assert "https://example.com/tutorial" in links
    assert "https://example.com/docs/api.md" in links
    assert "https://example.com/quick" in links


def test_parse_llms_txt_links_deduplicates():
    """Duplicate links should be removed, preserving first occurrence order."""
    content = """
[Link 1](https://example.com/a)
[Link 2](https://example.com/b)
[Link 1 again](https://example.com/a)
[Link 3](https://example.com/c)
"""
    links = parse_llms_txt_links(content, "https://example.com/llms.txt")
    assert len(links) == 3
    assert links == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]


def test_is_same_site_returns_true_for_same_site():
    assert is_same_site("https://example.com/llms.txt", "https://example.com/docs/install.md")


def test_is_same_site_returns_false_for_different_site():
    assert not is_same_site("https://example.com/llms.txt", "https://other.com/docs/")


def test_extract_domain():
    assert extract_domain("https://llmstext.org/docs/hooks.md") == "llmstext.org"
    # Subdomains are preserved in .value
    assert extract_domain("https://api.example.com/v1/") == "api.example.com"


def test_extract_path():
    assert extract_path("https://llmstext.org/docs/hooks.md") == "/docs/hooks.md"
    assert extract_path("https://example.com/") == "/"


# =============================================================================
# Domain value object tests
# =============================================================================


def test_domain_preserves_subdomains():
    """Subdomains should be preserved in .value."""
    assert Domain("www.example.com").value == "www.example.com"
    assert Domain("api.example.com").value == "api.example.com"
    assert Domain("docs.api.example.com").value == "docs.api.example.com"
    assert Domain("https://cdn.docs.example.com/file.js").value == "cdn.docs.example.com"


def test_domain_handles_country_code_tlds():
    """Country-code TLDs like .co.uk should be handled correctly."""
    assert Domain("bbc.co.uk").value == "bbc.co.uk"
    assert Domain("forums.bbc.co.uk").value == "forums.bbc.co.uk"
    assert Domain("https://www.bbc.co.uk/news").value == "www.bbc.co.uk"


def test_domain_registrable_domain_property():
    """registrable_domain should return eTLD+1."""
    assert Domain("example.com").registrable_domain == "example.com"
    assert Domain("www.example.com").registrable_domain == "example.com"
    assert Domain("api.docs.example.com").registrable_domain == "example.com"
    assert Domain("forums.bbc.co.uk").registrable_domain == "bbc.co.uk"


def test_domain_equality():
    """Different URLs with same registrable domain should be equal."""
    assert Domain("example.com") == Domain("www.example.com")
    assert Domain("api.example.com") == Domain("docs.example.com")
    assert Domain("https://example.com") == Domain("http://www.example.com:8080/path")


def test_domain_inequality():
    """Different registrable domains should not be equal."""
    assert Domain("example.com") != Domain("example.org")
    assert Domain("bbc.co.uk") != Domain("cnn.com")


def test_is_same_site_with_subdomains():
    """is_same_site should match subdomains of the same registrable domain."""
    assert is_same_site("https://example.com/", "https://api.example.com/docs")
    assert is_same_site("https://docs.example.com/", "https://www.example.com/")
    assert is_same_site("https://forums.bbc.co.uk/", "https://news.bbc.co.uk/")


# =============================================================================
# Content type validation tests
# =============================================================================


def test_is_markdown_content_accepts_markdown():
    """Accept standard markdown content types."""
    assert is_markdown_content("text/markdown")
    assert is_markdown_content("text/x-markdown")
    assert is_markdown_content("text/plain")


def test_is_markdown_content_accepts_with_charset():
    """Accept content types with charset parameters."""
    assert is_markdown_content("text/markdown; charset=utf-8")
    assert is_markdown_content("text/plain; charset=utf-8")
    assert is_markdown_content("text/plain;charset=UTF-8")


def test_is_markdown_content_rejects_html():
    """Reject HTML and other non-markdown types."""
    assert not is_markdown_content("text/html")
    assert not is_markdown_content("text/html; charset=utf-8")
    assert not is_markdown_content("application/json")
    assert not is_markdown_content("image/png")


def test_is_markdown_content_rejects_missing():
    """Reject missing/empty content type (don't trust unknown content)."""
    assert not is_markdown_content(None)
    assert not is_markdown_content("")
