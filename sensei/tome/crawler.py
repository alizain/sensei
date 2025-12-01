"""Crawler for llms.txt documentation sources using Crawlee."""

import hashlib
import logging
from datetime import timedelta

from crawlee import ConcurrencySettings, Request
from crawlee.crawlers import HttpCrawler, HttpCrawlingContext
from crawlee.storage_clients import MemoryStorageClient

from sensei.database.storage import save_document_metadata, save_sections
from sensei.tome.chunker import chunk_markdown
from sensei.tome.parser import extract_path, is_same_domain, parse_llms_txt_links
from sensei.types import Domain, IngestResult, SaveResult, Success, TransientError

logger = logging.getLogger(__name__)

# Crawler configuration
REQUEST_TIMEOUT = timedelta(seconds=30)
MAX_REQUESTS_PER_CRAWL = 500
CONCURRENCY = ConcurrencySettings(min_concurrency=1, max_concurrency=10)

# Content types we accept (llms.txt standard uses markdown)
# Many servers serve .md files as text/plain, so we accept both
ALLOWED_CONTENT_TYPES = frozenset({"text/markdown", "text/plain", "text/x-markdown"})


def content_hash(content: str) -> str:
	"""Generate a hash for content change detection."""
	return hashlib.sha256(content.encode()).hexdigest()[:16]


def is_markdown_content(content_type: str | None) -> bool:
	"""Check if content type indicates markdown or plain text.

	Args:
	    content_type: The Content-Type header value (may include charset)

	Returns:
	    True if content type is acceptable for markdown content
	"""
	if not content_type:
		return True  # Accept if no content type (trust the URL)
	# Extract media type (ignore charset and other parameters)
	media_type = content_type.split(";")[0].strip().lower()
	return media_type in ALLOWED_CONTENT_TYPES


async def ingest_domain(domain: str, max_depth: int = 3) -> Success[IngestResult]:
	"""Ingest documentation from a domain's llms.txt and llms-full.txt files.

	Fetches both /llms.txt (INDEX) and /llms-full.txt (FULL) from the domain,
	parses llms.txt to extract links, then crawls all same-domain linked
	documents up to max_depth. Missing llms-full.txt (404) is handled gracefully.

	Documents are chunked by markdown headings and stored as sections for
	efficient full-text search and granular retrieval.

	Args:
	    domain: The domain to crawl (e.g., "react.dev"). Can be a full URL -
	            will be normalized automatically.
	    max_depth: Maximum link depth to follow. 0 means only fetch llms.txt
	            and llms-full.txt (no linked documents). 1 means fetch those
	            plus direct links. Default is 3.

	Returns:
	    Success[IngestResult] with counts of documents processed

	Raises:
	    TransientError: If the crawl fails due to network issues
	"""
	# Normalize domain (handles full URLs, www prefix, ports, etc.)
	normalized_domain = Domain(domain).value
	result = IngestResult(domain=normalized_domain)

	# Start with both llms.txt (INDEX) and llms-full.txt (FULL)
	# llms-full.txt may not exist (404 is handled gracefully by Crawlee)
	initial_urls = [
		f"https://{normalized_domain}/llms.txt",
		f"https://{normalized_domain}/llms-full.txt",
	]

	# Use MemoryStorageClient to avoid filesystem race conditions between crawls
	# This eliminates the need for cleanup and prevents state conflicts
	storage_client = MemoryStorageClient()

	crawler = HttpCrawler(
		max_requests_per_crawl=MAX_REQUESTS_PER_CRAWL,
		request_handler_timeout=REQUEST_TIMEOUT,
		concurrency_settings=CONCURRENCY,
		storage_client=storage_client,
	)

	@crawler.router.default_handler
	async def handle_document(context: HttpCrawlingContext) -> None:
		"""Handle any markdown document (llms.txt or linked docs)."""
		# Use loaded_url (after redirects) for accurate domain matching
		url = context.request.loaded_url or context.request.url
		current_depth = context.request.user_data.get("depth", 0)
		logger.info(f"Processing document (depth={current_depth}): {url}")

		# Check content type before reading body
		content_type = context.http_response.headers.get("content-type")
		if not is_markdown_content(content_type):
			logger.warning(f"Skipping non-markdown content type '{content_type}': {url}")
			result.errors.append(f"Invalid content type '{content_type}': {url}")
			return

		try:
			content = (await context.http_response.read()).decode("utf-8")
		except UnicodeDecodeError:
			logger.warning(f"Skipping non-text content: {url}")
			result.errors.append(f"Non-text content: {url}")
			return

		# Save document metadata (no content - that goes in sections)
		hash_value = content_hash(content)
		save_result, doc_id = await save_document_metadata(
			domain=normalized_domain,
			url=url,
			path=extract_path(url),
			content_hash=hash_value,
			depth=current_depth,
		)

		match save_result:
			case SaveResult.INSERTED:
				result.documents_added += 1
			case SaveResult.UPDATED:
				result.documents_updated += 1
			case SaveResult.SKIPPED:
				result.documents_skipped += 1

		# Only chunk and save sections if document was inserted or updated
		if save_result != SaveResult.SKIPPED and doc_id:
			# Chunk markdown into sections
			sections = chunk_markdown(content)
			# Save sections with parent relationships
			await save_sections(doc_id, sections)
			logger.debug(f"Saved sections for {url}")

		# Parse links and enqueue same-domain ones if within depth limit
		if current_depth < max_depth:
			all_links = parse_llms_txt_links(content, url)
			same_domain_links = [link for link in all_links if is_same_domain(url, link)]
			if same_domain_links:
				logger.info(f"Found {len(all_links)} links, {len(same_domain_links)} same-domain, enqueueing")
				requests = [
					Request.from_url(link, user_data={"depth": current_depth + 1}) for link in same_domain_links
				]
				await context.add_requests(requests)

	# Start crawl with both llms.txt and llms-full.txt (both depth=0)
	try:
		initial_requests = [Request.from_url(url, user_data={"depth": 0}) for url in initial_urls]
		await crawler.run(initial_requests)
	except Exception as e:
		logger.error(f"Crawl failed for {normalized_domain}: {e}")
		raise TransientError(f"Crawl failed for {normalized_domain}: {e}") from e

	logger.info(
		f"Ingest complete for {normalized_domain}: "
		f"added={result.documents_added}, "
		f"updated={result.documents_updated}, "
		f"skipped={result.documents_skipped}, "
		f"errors={len(result.errors)}"
	)
	return Success(result)
