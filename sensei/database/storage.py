"""Database operations for Sensei using SQLAlchemy with async PostgreSQL."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import Integer, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sensei.config import settings
from sensei.database.models import Document, Query, Section
from sensei.database.models import Rating as RatingModel
from sensei.types import CacheHit, Rating, SearchResult

logger = logging.getLogger(__name__)

# Lazy-initialized engine and session factory
_engine = None
_async_session_local = None


def _get_engine():
    """Get or create the async engine (lazy initialization)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
        )
    return _engine


def _get_session_factory():
    """Get or create the async session factory (lazy initialization)."""
    global _async_session_local
    if _async_session_local is None:
        _async_session_local = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_local


def AsyncSessionLocal():
    """Get a session from the lazy-initialized factory."""
    return _get_session_factory()()


def _to_cache_hit(q: Query, age_days: int) -> CacheHit:
    """Convert SQLAlchemy Query + computed age_days to CacheHit."""
    data = {k: getattr(q, k) for k in CacheHit.model_fields if k != "age_days"}
    data["age_days"] = age_days
    return CacheHit(**data)


async def save_query(
    query: str,
    output: str,
    messages: bytes | None = None,
    language: Optional[str] = None,
    library: Optional[str] = None,
    version: Optional[str] = None,
    parent_id: Optional[UUID] = None,
) -> UUID:
    """Save a query and its response to the database.

    Args:
        query: The user's query string
        output: The final text output from the agent
        messages: JSON bytes of all intermediate messages (from result.new_messages_json())
        language: Optional programming language filter
        library: Optional library/framework name
        version: Optional version specification
        parent_id: Optional parent query ID for sub-queries

    Returns:
        The generated UUID for the saved query
    """
    logger.info(f"Saving query to database: parent={parent_id}")
    async with AsyncSessionLocal() as session:
        query_record = Query(
            query=query,
            language=language,
            library=library,
            version=version,
            output=output,
            messages=messages.decode("utf-8") if messages else None,
            parent_id=parent_id,
        )
        session.add(query_record)
        await session.commit()
        await session.refresh(query_record)
        logger.debug(f"Query saved: id={query_record.id}")
        return query_record.id


async def save_rating(rating: Rating) -> None:
    """Save a rating for a query response."""
    logger.info(f"Saving rating to database: query_id={rating.query_id}")
    async with AsyncSessionLocal() as session:
        rating_record = RatingModel(
            query_id=rating.query_id,
            correctness=rating.correctness,
            relevance=rating.relevance,
            usefulness=rating.usefulness,
            reasoning=rating.reasoning,
            agent_model=rating.agent_model,
            agent_system=rating.agent_system,
            agent_version=rating.agent_version,
        )
        session.add(rating_record)
        await session.commit()
    logger.debug(
        f"Rating saved: query_id={rating.query_id}, scores=({rating.correctness}, {rating.relevance}, {rating.usefulness})"
    )


async def get_query(id: UUID) -> Optional[Query]:
    """Retrieve a query by its ID.

    Args:
        id: The query ID to retrieve

    Returns:
        Query object if found, None otherwise
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Query).where(Query.id == id))
        return result.scalar_one_or_none()


async def search_queries(
    query: str,
    limit: int = 10,
) -> list[CacheHit]:
    """Search cached queries using PostgreSQL full-text search.

    Uses websearch_to_tsquery for natural language query parsing
    and ts_rank for relevance ordering.

    Args:
        query: Natural language search query
        limit: Maximum results to return

    Returns:
        List of CacheHit objects
    """
    logger.debug(f"Search queries: query={query}")

    if not query.strip():
        return []

    async with AsyncSessionLocal() as session:
        # Compute age_days in SQL: EXTRACT(DAY FROM NOW() - inserted_at)::int
        age_days_expr = func.extract("day", func.now() - Query.inserted_at).cast(Integer).label("age_days")
        tsquery = func.websearch_to_tsquery("english", query)

        stmt = (
            select(Query, age_days_expr)
            .where(Query.query_tsvector.op("@@")(tsquery))
            .order_by(func.ts_rank(Query.query_tsvector, tsquery).desc())
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()

    return [_to_cache_hit(q, age) for q, age in rows]


async def insert_document(
    domain: str,
    url: str,
    path: str,
    content_hash: str,
    generation_id: UUID,
) -> UUID:
    """Insert a new document for a generation (no upsert logic).

    With generation-based crawls, we always insert new documents for each crawl.
    Old documents are cleaned up after the generation swap.

    Note: Content is stored in sections, not documents.
    Call insert_sections() after this to save the content.

    Args:
        domain: Source domain (e.g., 'llmstext.org')
        url: Full URL of the document
        path: Path portion of the URL
        content_hash: Hash for change detection (future optimization)
        generation_id: The generation this document belongs to

    Returns:
        The generated document ID
    """
    async with AsyncSessionLocal() as session:
        db_doc = Document(
            domain=domain,
            url=url,
            path=path,
            content_hash=content_hash,
            generation_id=generation_id,
            generation_active=False,  # Not visible until generation swap
        )
        session.add(db_doc)
        await session.commit()
        await session.refresh(db_doc)
        logger.info(f"Document inserted: {url} (generation={generation_id})")
        return db_doc.id


async def activate_generation(domain: str, generation_id: UUID) -> int:
    """Atomically swap to a new generation for a domain.

    Sets generation_active = (generation_id == new_generation_id) for all
    documents in the domain. This makes the new generation visible and
    hides all previous generations in one atomic operation.

    Args:
        domain: The domain to swap generations for
        generation_id: The new generation to activate

    Returns:
        Number of documents activated
    """
    async with AsyncSessionLocal() as session:
        # Atomic swap: active = (generation_id == new_gen_id)
        result = await session.execute(
            text("""
				UPDATE documents
				SET generation_active = (generation_id = :gen_id)
				WHERE domain = :domain
				RETURNING id
			"""),
            {"domain": domain, "gen_id": str(generation_id)},
        )
        count = len(result.fetchall())
        await session.commit()
        logger.info(f"Activated generation {generation_id} for {domain}: {count} documents")
        return count


async def cleanup_old_generations(domain: str) -> int:
    """Delete inactive documents for a domain.

    Should be called after activate_generation to clean up old generations.
    Sections are deleted via CASCADE.

    Args:
        domain: The domain to clean up

    Returns:
        Number of documents deleted
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(Document).where(
                Document.domain == domain,
                Document.generation_active == False,  # noqa: E712 - SQLAlchemy comparison
            )
        )
        await session.commit()
        count = result.rowcount
        logger.info(f"Cleaned up {count} old documents for {domain}")
        return count


async def insert_sections(sections: list[Section]) -> int:
    """Insert sections into the database.

    Expects Section models with all relationships already set
    (via flatten_section_tree in crawler.py).

    Args:
        sections: Flat list of Section models to insert

    Returns:
        Number of sections inserted
    """
    if not sections:
        return 0

    async with AsyncSessionLocal() as session:
        session.add_all(sections)
        await session.commit()

        doc_id = sections[0].document_id if sections else None
        logger.info(f"Inserted {len(sections)} sections for document {doc_id}")
        return len(sections)


async def delete_sections_by_document(document_id: UUID) -> int:
    """Delete all sections for a document.

    Args:
        document_id: The document to delete sections for

    Returns:
        Number of sections deleted
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(Section).where(Section.document_id == document_id))
        await session.commit()
        return result.rowcount


async def get_sections_by_document(
    domain: str,
    path: str,
) -> list[Section]:
    """Get all sections for an active document, ordered by position.

    Used for reconstructing the full document content.
    Only returns sections from active (visible) documents.

    Args:
        domain: Document domain
        path: Document path

    Returns:
        List of Section objects ordered by position
    """
    async with AsyncSessionLocal() as session:
        # Single query with JOIN instead of two separate queries
        result = await session.execute(
            select(Section)
            .join(Document, Document.id == Section.document_id)
            .where(
                Document.domain == domain,
                Document.path == path,
                Document.generation_active == True,  # noqa: E712 - SQLAlchemy comparison
            )
            .order_by(Section.position)
        )
        return list(result.scalars().all())


async def get_document_by_url(url: str, active_only: bool = True) -> Optional[Document]:
    """Retrieve a document by its URL.

    Args:
        url: The full URL of the document
        active_only: If True (default), only return active documents

    Returns:
        Document if found, None otherwise
    """
    async with AsyncSessionLocal() as session:
        query = select(Document).where(Document.url == url)
        if active_only:
            query = query.where(Document.generation_active == True)  # noqa: E712
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def delete_documents_by_domain(domain: str) -> int:
    """Delete all documents for a domain.

    Useful for re-crawling a domain from scratch.

    Args:
        domain: The domain to delete documents for

    Returns:
        Number of documents deleted
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(delete(Document).where(Document.domain == domain))
        await session.commit()
        count = result.rowcount
        logger.info(f"Deleted {count} documents for domain: {domain}")
        return count


async def search_sections_fts(
    domain: str,
    query: str,
    path_prefixes: list[str] | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    """Search sections using PostgreSQL full-text search.

    Uses websearch_to_tsquery() for natural language query parsing,
    ts_headline() for snippets, and precomputed heading_path column.

    Args:
        domain: Domain to search within (required)
        query: Natural language search query
        path_prefixes: Optional LIKE patterns for path filtering (e.g., ["/hooks%"])
                      Should already be normalized (start with /, end with %)
        limit: Maximum results to return

    Returns:
        List of SearchResult objects
    """
    logger.debug(f"FTS search: domain={domain}, query={query}, path_prefixes={path_prefixes}")

    if not query.strip():
        return []

    async with AsyncSessionLocal() as session:
        # Simple query using precomputed heading_path column
        # Only search active documents (generation_active = true)
        sql = """
            SELECT
                d.url,
                d.path,
                ts_headline('english', s.content, websearch_to_tsquery('english', :query),
                           'MaxWords=50, MinWords=20, StartSel=**, StopSel=**') as snippet,
                ts_rank(s.content_tsvector, websearch_to_tsquery('english', :query)) as rank,
                s.heading_path
            FROM sections s
            JOIN documents d ON s.document_id = d.id
            WHERE d.domain = :domain
              AND d.generation_active = true
              AND s.content_tsvector @@ websearch_to_tsquery('english', :query)
        """

        params: dict = {"domain": domain, "query": query, "limit": limit}

        # Add path prefix filtering if specified (expects pre-normalized LIKE patterns)
        if path_prefixes:
            path_conditions = " OR ".join([f"d.path LIKE :path{i}" for i in range(len(path_prefixes))])
            sql += f" AND ({path_conditions})"
            for i, prefix in enumerate(path_prefixes):
                params[f"path{i}"] = prefix

        sql += """
            ORDER BY rank DESC
            LIMIT :limit
        """

        result = await session.execute(text(sql), params)
        rows = result.fetchall()

        return [
            SearchResult(
                url=row.url,
                path=row.path,
                snippet=row.snippet,
                rank=row.rank,
                heading_path=row.heading_path or "",
            )
            for row in rows
        ]
