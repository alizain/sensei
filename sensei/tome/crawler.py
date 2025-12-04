"""Crawler for llms.txt documentation sources using Crawlee.

Generation-based crawling:
1. Each crawl creates a new generation (UUID)
2. All documents are inserted with generation_active=false
3. After crawl completes, atomically swap: activate new generation, deactivate old
4. Cleanup deletes inactive documents

This ensures queries always see a complete, consistent set of documents.
"""

import hashlib
import logging
from datetime import timedelta
from uuid import UUID, uuid4

from crawlee import ConcurrencySettings, Request
from crawlee.crawlers import BasicCrawlingContext, HttpCrawler, HttpCrawlingContext
from crawlee.errors import HttpStatusCodeError
from crawlee.storage_clients import MemoryStorageClient
from impit import TransportError
from sqlalchemy.exc import IntegrityError

from sensei.database.models import Section
from sensei.database.storage import (
    activate_generation,
    cleanup_old_generations,
    insert_document,
    insert_sections,
)
from sensei.tome.chunker import SectionData, chunk_markdown
from sensei.tome.parser import extract_path, is_same_site, parse_llms_txt_links
from sensei.types import (
    ContentTypeWarning,
    Domain,
    IngestResult,
    NoLLMsTxt,
    NotFoundWarning,
    Success,
    TransientError,
)

logger = logging.getLogger(__name__)

# Crawler configuration
REQUEST_TIMEOUT = timedelta(seconds=30)
MAX_REQUESTS_PER_CRAWL = 1000000
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
        return False
    # Extract media type (ignore charset and other parameters)
    media_type = content_type.split(";")[0].strip().lower()
    return media_type in ALLOWED_CONTENT_TYPES


def flatten_section_tree(
    root: SectionData,
    document_id: UUID,
) -> list[Section]:
    """Convert SectionData tree to flat list of Section models with parent relationships.

    Tree traversal is business logic (understanding document structure), not storage logic.
    This function flattens the tree by pre-generating UUIDs for each section, allowing
    child sections to reference their parent's ID before database insertion.

    Also computes heading_path for each section (e.g., "API > Hooks > useState") to
    avoid expensive recursive CTE on every FTS search query.

    Args:
        root: Root SectionData from chunker containing the tree structure
        document_id: UUID of the document these sections belong to

    Returns:
        Flat list of Section models with parent_section_id relationships set,
        ordered by position for document reconstruction.
    """
    sections: list[Section] = []
    position = [0]  # Use list to allow mutation in nested function

    def walk(node: SectionData, parent_id: UUID | None, path_parts: list[str]) -> None:
        # Only create section if there's content or children
        if node.content or node.children:
            # Build heading path from ancestors + current heading
            current_path = path_parts + ([node.heading] if node.heading else [])
            heading_path = " > ".join(current_path) if current_path else None

            section = Section(
                document_id=document_id,
                parent_section_id=parent_id,
                heading=node.heading,
                level=node.level,
                content=node.content or "",  # Ensure non-null for DB constraint
                position=position[0],
                heading_path=heading_path,
            )
            position[0] += 1
            sections.append(section)

            # Recurse with this section's ID as parent and updated path
            for child in node.children:
                walk(child, section.id, current_path)

    walk(root, None, [])
    return sections


async def ingest_domain(domain: str, max_depth: int = 10) -> Success[IngestResult] | NoLLMsTxt:
    """Ingest documentation from a domain's llms.txt file.

    Fetches /llms.txt from the domain, parses it to extract links, then crawls
    all same-domain linked documents up to max_depth.

    Uses generation-based crawling for atomic visibility:
    1. Creates a new generation UUID for this crawl
    2. Inserts all documents with generation_active=false
    3. After crawl completes, atomically activates the new generation
    4. Cleans up old (inactive) documents

    Args:
        domain: The domain to crawl (e.g., "llmstext.org"). Can be a full URL -
                will be normalized automatically.
        max_depth: Maximum link depth to follow. 0 means only fetch llms.txt
                (no linked documents). 1 means fetch llms.txt plus direct links.
                Default is 10.

    Returns:
        Success[IngestResult] with counts of documents processed
        NoLLMsTxt if the domain does not have an /llms.txt file

    Raises:
        TransientError: If the crawl fails due to network issues
    """
    # Normalize domain (handles full URLs, www prefix, ports, etc.)
    normalized_domain = Domain(domain).value
    result = IngestResult(domain=normalized_domain)

    # Create a new generation for this crawl
    generation_id = uuid4()
    logger.info(f"Starting crawl for {normalized_domain} with generation {generation_id}")

    # Start with llms.txt - the standard entry point for documentation
    llms_txt_url = f"https://{normalized_domain}/llms.txt"

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
            result.warnings.append(ContentTypeWarning(url, content_type))
            return

        try:
            content = (await context.http_response.read()).decode("utf-8")
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode content: {url}")
            result.failures.append(e)
            return

        # Insert document for this generation (not yet visible to queries)
        hash_value = content_hash(content)
        doc_id = await insert_document(
            domain=normalized_domain,
            url=url,
            path=extract_path(url),
            content_hash=hash_value,
            generation_id=generation_id,
        )
        result.documents_added += 1

        # Chunk markdown, flatten tree, and insert sections
        section_tree = chunk_markdown(content)
        sections = flatten_section_tree(section_tree, doc_id)
        await insert_sections(sections)
        logger.debug(f"Inserted {len(sections)} sections for {url}")

        # Parse links and enqueue same-domain ones if within depth limit
        if current_depth < max_depth:
            all_links = parse_llms_txt_links(content, url)
            same_site_links = [link for link in all_links if is_same_site(url, link)]
            other_site_links = [link for link in all_links if not is_same_site(url, link)]

            # Debug logging for link analysis
            logger.debug(f"=== Link analysis for {url} ===")
            logger.debug(f"Same-site links ({len(same_site_links)}):")
            for link in same_site_links:
                logger.debug(f"  ✓ {link}")
            logger.debug(f"Other-site links ({len(other_site_links)}):")
            for link in other_site_links:
                logger.debug(f"  ✗ {link}")

            if same_site_links:
                logger.info(f"Found {len(all_links)} links, {len(same_site_links)} same-site, enqueueing")
                requests = [Request.from_url(link, user_data={"depth": current_depth + 1}) for link in same_site_links]
                await context.add_requests(requests)

    @crawler.error_handler
    async def handle_error(context: BasicCrawlingContext, error: Exception) -> None:
        """Prevent retries for deterministic errors.

        For errors where retrying won't help:
        - Set no_retry=True → skips retries, goes to failed_request_handler
        - Raise → stops crawler entirely (only for data corruption risks)

        Non-retryable errors:
        - DNS errors: Domain doesn't exist, retrying won't resolve it
        - IntegrityError: Database constraint violations (raises to stop crawler)
        """
        # Check the wrapped exception for RequestHandlerError
        actual_error = error
        if hasattr(error, "wrapped_exception"):
            actual_error = error.wrapped_exception

        # DNS errors are deterministic - no point retrying
        if isinstance(actual_error, TransportError) and "dns error" in str(actual_error).lower():
            logger.debug(f"DNS error (no retry): {context.request.url}")
            context.request.no_retry = True
            return  # Let it go to failed_request_handler

        if isinstance(actual_error, IntegrityError):
            logger.error(f"Non-retryable error, aborting: {context.request.url}: {actual_error}")
            raise actual_error

    @crawler.failed_request_handler
    async def handle_failed_request(context: BasicCrawlingContext, error: Exception) -> None:
        """Handle requests that failed after all retries.

        Categorizes errors:
        - 404 → warning (dead links are expected in documentation)
        - DNS errors → warning (domain doesn't exist, common in docs)
        - Other HTTP errors, network errors → failure (unexpected)
        """
        url = context.request.url

        # 404s are expected (dead links in docs) - wrap with URL, chain original
        if isinstance(error, HttpStatusCodeError) and error.status_code == 404:
            logger.warning(f"Not found (404): {url}")
            warning = NotFoundWarning(url)
            warning.__cause__ = error  # Preserve original for debugging
            result.warnings.append(warning)
        # DNS errors are expected (domains disappear, typos in docs)
        elif isinstance(error, TransportError) and "dns error" in str(error).lower():
            logger.warning(f"DNS error (domain not found): {url}")
            result.warnings.append(error)
        else:
            # All other errors are failures
            logger.error(f"Request failed ({type(error).__name__}): {url} - {error}")
            result.failures.append(error)

    # Start crawl with llms.txt (depth=0)
    try:
        initial_request = Request.from_url(llms_txt_url, user_data={"depth": 0})
        await crawler.run([initial_request])
    except Exception as e:
        logger.error(f"Crawl failed for {normalized_domain}: {e}")
        # Don't activate - leave orphan generation for cleanup
        raise TransientError(f"Crawl failed for {normalized_domain}: {e}") from e

    # Check if llms.txt was not found (inspect warnings after crawl)
    llms_txt_missing = any(isinstance(w, NotFoundWarning) and w.url == llms_txt_url for w in result.warnings)
    if llms_txt_missing:
        return NoLLMsTxt(domain=normalized_domain)

    # Crawl succeeded - atomically swap to new generation
    await activate_generation(normalized_domain, generation_id)

    # Clean up old generations (non-blocking, can fail without affecting queries)
    try:
        deleted = await cleanup_old_generations(normalized_domain)
        logger.info(f"Cleaned up {deleted} old documents for {normalized_domain}")
    except Exception as e:
        # Cleanup failure is unexpected - record as failure
        logger.error(f"Cleanup failed for {normalized_domain}: {e}")
        result.failures.append(e)

    logger.info(
        f"Ingest complete for {normalized_domain}: "
        f"added={result.documents_added}, "
        f"generation={generation_id}, "
        f"warnings={len(result.warnings)}, "
        f"failures={len(result.failures)}"
    )
    return Success(result)
