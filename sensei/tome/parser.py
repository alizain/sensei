"""Parser for llms.txt files and link extraction."""

from urllib.parse import urljoin, urlparse

from markdown_it import MarkdownIt
from markdown_it.token import Token

from sensei.types import Domain

# Singleton markdown parser
_md = MarkdownIt()


def parse_llms_txt_links(content: str, base_url: str) -> list[str]:
	"""Extract all links from an llms.txt file.

	Uses markdown-it-py to extract links from all markdown formats:
	- Inline links: [text](url)
	- Reference links: [text][ref] with [ref]: url definitions
	- Autolinks: <https://example.com>

	Args:
	    content: The markdown content of the llms.txt file
	    base_url: The URL of the llms.txt file (for resolving relative links)

	Returns:
	    List of absolute URLs found in the document (deduplicated, order preserved)
	"""
	tokens = _md.parse(content)
	raw_urls = _extract_urls_from_tokens(tokens)

	# Resolve relative URLs and deduplicate while preserving order
	seen: set[str] = set()
	links: list[str] = []

	for url in raw_urls:
		# Skip anchor-only links
		if url.startswith("#"):
			continue
		# Skip mailto links
		if url.startswith("mailto:"):
			continue
		# Resolve relative URLs
		absolute_url = urljoin(base_url, url)
		# Deduplicate
		if absolute_url not in seen:
			seen.add(absolute_url)
			links.append(absolute_url)

	return links


def _extract_urls_from_tokens(tokens: list[Token]) -> list[str]:
	"""Extract URLs from markdown-it-py tokens.

	Handles:
	- link_open tokens (inline and reference-style, autolinks)

	Args:
	    tokens: List of markdown-it-py tokens

	Returns:
	    List of URLs found in the tokens
	"""
	urls: list[str] = []

	for token in tokens:
		# Link tokens have href in attrs
		if token.type == "link_open":
			href = token.attrGet("href")
			if href:
				urls.append(href)

		# Recursively check children
		if token.children:
			urls.extend(_extract_urls_from_tokens(token.children))

	return urls


def is_same_domain(base_url: str, target_url: str) -> bool:
	"""Check if target_url is on the same domain as base_url.

	Uses Domain value object for normalization:
	- www.example.com == example.com
	- example.com:443 == example.com
	- EXAMPLE.COM == example.com

	Args:
	    base_url: The reference URL (e.g., llms.txt location)
	    target_url: The URL to check

	Returns:
	    True if both URLs share the same normalized domain
	"""
	return Domain.from_url(base_url) == Domain.from_url(target_url)


def extract_path(url: str) -> str:
	"""Extract the path portion from a URL.

	Args:
	    url: Full URL

	Returns:
	    Path portion (e.g., "/docs/hooks/useState.md")
	"""
	return urlparse(url).path or "/"


def extract_domain(url: str) -> str:
	"""Extract the normalized domain from a URL.

	Args:
	    url: Full URL

	Returns:
	    Normalized domain (e.g., "react.dev")
	"""
	return Domain.from_url(url).value
