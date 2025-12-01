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
from crawlee.crawlers import HttpCrawler, HttpCrawlingContext
from crawlee.storage_clients import MemoryStorageClient

from sensei.database.models import Section
from sensei.database.storage import (
    activate_generation,
    cleanup_old_generations,
    insert_document,
    save_sections,
)
from sensei.tome.chunker import SectionData, chunk_markdown
from sensei.tome.parser import extract_path, is_same_domain, parse_llms_txt_links
from sensei.types import Domain, IngestResult, Success, TransientError

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

    Args:
        root: Root SectionData from chunker containing the tree structure
        document_id: UUID of the document these sections belong to

    Returns:
        Flat list of Section models with parent_section_id relationships set,
        ordered by position for document reconstruction.
    """
    sections: list[Section] = []
    position = [0]  # Use list to allow mutation in nested function

    def walk(node: SectionData, parent_id: UUID | None) -> None:
        # Only create section if there's content or children
        if node.content or node.children:
            section = Section(
                document_id=document_id,
                parent_section_id=parent_id,
                heading=node.heading,
                level=node.level,
                content=node.content or "",  # Ensure non-null for DB constraint
                position=position[0],
            )
            position[0] += 1
            sections.append(section)

            # Recurse with this section's ID as parent
            for child in node.children:
                walk(child, section.id)

    walk(root, None)
    return sections


async def ingest_domain(domain: str, max_depth: int = 3) -> Success[IngestResult]:
    """Ingest documentation from a domain's llms.txt file.

    Fetches /llms.txt from the domain, parses it to extract links, then crawls
    all same-domain linked documents up to max_depth.

    Uses generation-based crawling for atomic visibility:
    1. Creates a new generation UUID for this crawl
    2. Inserts all documents with generation_active=false
    3. After crawl completes, atomically activates the new generation
    4. Cleans up old (inactive) documents

    Args:
        domain: The domain to crawl (e.g., "react.dev"). Can be a full URL -
                will be normalized automatically.
        max_depth: Maximum link depth to follow. 0 means only fetch llms.txt
                (no linked documents). 1 means fetch llms.txt plus direct links.
                Default is 3.

    Returns:
        Success[IngestResult] with counts of documents processed

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
    initial_urls = [
        f"https://{normalized_domain}/llms.txt",
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

        # Chunk markdown, flatten tree, and save sections
        section_tree = chunk_markdown(content)
        sections = flatten_section_tree(section_tree, doc_id)
        await save_sections(doc_id, sections)
        logger.debug(f"Saved {len(sections)} sections for {url}")

        # Parse links and enqueue same-domain ones if within depth limit
        if current_depth < max_depth:
            all_links = parse_llms_txt_links(content, url)
            same_domain_links = [link for link in all_links if is_same_domain(url, link)]
            other_domain_links = [link for link in all_links if not is_same_domain(url, link)]

            # Debug logging for link analysis
            logger.debug(f"=== Link analysis for {url} ===")
            logger.debug(f"Same-domain links ({len(same_domain_links)}):")
            for link in same_domain_links:
                logger.debug(f"  ✓ {link}")
            logger.debug(f"Other-domain links ({len(other_domain_links)}):")
            for link in other_domain_links:
                logger.debug(f"  ✗ {link}")

            if same_domain_links:
                logger.info(f"Found {len(all_links)} links, {len(same_domain_links)} same-domain, enqueueing")
                requests = [
                    Request.from_url(link, user_data={"depth": current_depth + 1}) for link in same_domain_links
                ]
                await context.add_requests(requests)

    # Start crawl with llms.txt (depth=0)
    try:
        initial_requests = [Request.from_url(url, user_data={"depth": 0}) for url in initial_urls]
        await crawler.run(initial_requests)
    except Exception as e:
        logger.error(f"Crawl failed for {normalized_domain}: {e}")
        # Don't activate - leave orphan generation for cleanup
        raise TransientError(f"Crawl failed for {normalized_domain}: {e}") from e

    # Crawl succeeded - atomically swap to new generation
    await activate_generation(normalized_domain, generation_id)

    # Clean up old generations (non-blocking, can fail without affecting queries)
    try:
        deleted = await cleanup_old_generations(normalized_domain)
        logger.info(f"Cleaned up {deleted} old documents for {normalized_domain}")
    except Exception as e:
        # Log but don't fail - cleanup is best-effort
        logger.warning(f"Cleanup failed for {normalized_domain}: {e}")
        result.errors.append(f"Cleanup failed: {e}")

    logger.info(
        f"Ingest complete for {normalized_domain}: "
        f"added={result.documents_added}, "
        f"generation={generation_id}, "
        f"errors={len(result.errors)}"
    )
    return Success(result)
