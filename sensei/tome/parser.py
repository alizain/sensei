"""Parser for llms.txt files and link extraction."""

from urllib.parse import urljoin, urlparse

from marko import Markdown
from marko.ast_renderer import ASTRenderer

from sensei.types import Domain

# Singleton markdown parser with AST renderer
_markdown_parser = Markdown(renderer=ASTRenderer)


def parse_llms_txt_links(content: str, base_url: str) -> list[str]:
	"""Extract all links from an llms.txt file.

	Uses the marko parser to extract links from all markdown formats:
	- Inline links: [text](url)
	- Reference links: [text][ref] with [ref]: url definitions
	- Autolinks: <https://example.com>

	Args:
	    content: The markdown content of the llms.txt file
	    base_url: The URL of the llms.txt file (for resolving relative links)

	Returns:
	    List of absolute URLs found in the document (deduplicated, order preserved)
	"""
	ast = _markdown_parser(content)
	raw_urls = _extract_urls_from_ast(ast)

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


def _extract_urls_from_ast(node: dict | list | str) -> list[str]:
	"""Recursively extract URLs from marko AST.

	Handles:
	- link elements (inline and reference-style)
	- auto_link elements (<url>)

	Args:
	    node: AST node (dict, list, or string)

	Returns:
	    List of URLs found in the AST
	"""
	urls: list[str] = []

	if isinstance(node, dict):
		element = node.get("element")

		# Regular links (inline and reference-style resolved)
		if element == "link":
			dest = node.get("dest")
			if dest:
				urls.append(dest)

		# Autolinks <url>
		elif element == "auto_link":
			dest = node.get("dest")
			if dest:
				urls.append(dest)

		# Traverse children
		children = node.get("children")
		if children:
			urls.extend(_extract_urls_from_ast(children))

	elif isinstance(node, list):
		for item in node:
			urls.extend(_extract_urls_from_ast(item))

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
