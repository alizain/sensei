"""Database operations for Sensei using SQLAlchemy with async PostgreSQL."""

import logging
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sensei.config import settings
from sensei.database.models import Document, Query, Section
from sensei.database.models import Rating as RatingModel
from sensei.types import CacheHit, Rating, SaveResult, SearchResult, SectionData

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


async def save_query(
	query: str,
	output: str,
	messages: bytes | None = None,
	language: Optional[str] = None,
	library: Optional[str] = None,
	version: Optional[str] = None,
	parent_id: Optional[UUID] = None,
	depth: int = 0,
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
	    depth: Recursion depth (0 = top-level)

	Returns:
	    The generated UUID for the saved query
	"""
	logger.info(f"Saving query to database: parent={parent_id}, depth={depth}")
	async with AsyncSessionLocal() as session:
		query_record = Query(
			query=query,
			language=language,
			library=library,
			version=version,
			output=output,
			messages=messages.decode("utf-8") if messages else None,
			parent_id=parent_id,
			depth=depth,
		)
		session.add(query_record)
		await session.commit()
		await session.refresh(query_record)
		logger.debug(f"Query saved: id={query_record.id}, depth={depth}")
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
	terms: list[str],
	limit: int = 10,
) -> list[CacheHit]:
	"""Search cached queries using ILIKE, AND-ing all terms.

	Each term is matched as a case-insensitive substring. All terms must match
	for a query to be included in results.

	Args:
	    terms: List of search terms (all must match via ILIKE)
	    limit: Maximum results to return

	Returns:
	    List of CacheHit objects
	"""
	logger.debug(f"Search: terms={terms}")

	if not terms:
		return []

	async with AsyncSessionLocal() as session:
		# Build WHERE clause: query ILIKE '%term1%' AND query ILIKE '%term2%' ...
		conditions = " AND ".join([f"query ILIKE :term{i}" for i in range(len(terms))])
		params: dict = {f"term{i}": f"%{term}%" for i, term in enumerate(terms)}
		params["limit"] = limit

		sql = f"""
            SELECT id, query, library, version, inserted_at
            FROM queries
            WHERE {conditions}
            LIMIT :limit
        """

		result = await session.execute(text(sql), params)
		rows = result.fetchall()

		now = datetime.now(UTC)
		hits = []
		for row in rows:
			query_id, query_text, lib, ver, inserted_at = row
			# inserted_at is timezone-aware from DB, no coercion needed
			age_days = (now - inserted_at).days if inserted_at else 0
			hits.append(
				CacheHit(
					query_id=query_id,
					query_truncated=query_text[:100] if query_text else "",
					age_days=age_days,
					library=lib,
					version=ver,
				)
			)
		return hits


async def save_document_metadata(
	domain: str,
	url: str,
	path: str,
	content_hash: str,
	depth: int = 0,
) -> tuple[SaveResult, UUID | None]:
	"""Save or update document metadata using upsert logic.

	If a document with the same URL exists:
	  - If content_hash matches, skip (SKIPPED) - returns existing doc ID
	  - If content_hash differs, update (UPDATED) - returns doc ID
	Otherwise, insert new document (INSERTED) - returns new doc ID

	Note: Content is now stored in sections, not documents.
	Call save_sections() after this to save the content.

	Args:
	    domain: Source domain (e.g., 'react.dev')
	    url: Full URL of the document
	    path: Path portion of the URL
	    content_hash: Hash for change detection
	    depth: Crawl depth (0 = llms.txt, 1+ = linked)

	Returns:
	    Tuple of (SaveResult, document_id or None if skipped)
	"""
	async with AsyncSessionLocal() as session:
		result = await session.execute(select(Document).where(Document.url == url))
		existing = result.scalar_one_or_none()

		if existing:
			if existing.content_hash == content_hash:
				logger.debug(f"Document unchanged, skipping: {url}")
				return SaveResult.SKIPPED, existing.id
			# Content changed - update metadata
			existing.content_hash = content_hash
			existing.depth = depth
			existing.content_refreshed_at = datetime.now(UTC)
			await session.commit()
			logger.info(f"Document updated: {url}")
			return SaveResult.UPDATED, existing.id

		db_doc = Document(
			domain=domain,
			url=url,
			path=path,
			content_hash=content_hash,
			depth=depth,
		)
		session.add(db_doc)
		await session.commit()
		await session.refresh(db_doc)
		logger.info(f"Document saved: {url}")
		return SaveResult.INSERTED, db_doc.id


async def save_sections(
	document_id: UUID,
	sections: SectionData,
) -> int:
	"""Save sections for a document, replacing any existing sections.

	Flattens the SectionData tree into rows with parent_section_id
	relationships and position ordering.

	Args:
	    document_id: The document these sections belong to
	    sections: Root SectionData containing the tree structure

	Returns:
	    Number of sections saved
	"""
	async with AsyncSessionLocal() as session:
		# Delete existing sections for this document (cascade will handle children)
		await session.execute(delete(Section).where(Section.document_id == document_id))

		# Flatten the tree and insert sections
		position_counter = [0]  # Use list to allow mutation in nested function

		def flatten(
			node: SectionData,
			parent_id: UUID | None = None,
		) -> list[Section]:
			"""Recursively flatten SectionData tree into Section models."""
			result: list[Section] = []

			# Create section for this node
			section = Section(
				document_id=document_id,
				parent_section_id=parent_id,
				heading=node.heading,
				level=node.level,
				content=node.content,
				position=position_counter[0],
			)
			position_counter[0] += 1
			result.append(section)

			# Recursively process children
			for child in node.children:
				# We need to flush to get the section ID for parent relationship
				session.add(section)

			return result

		# Alternative: flatten iteratively to get IDs properly
		async def save_tree(
			node: SectionData,
			parent_id: UUID | None = None,
		) -> int:
			"""Recursively save SectionData tree, returning count."""
			count = 0

			# Only save if there's content or children
			if node.content or node.children:
				section = Section(
					document_id=document_id,
					parent_section_id=parent_id,
					heading=node.heading,
					level=node.level,
					content=node.content,
					position=position_counter[0],
				)
				position_counter[0] += 1
				session.add(section)
				await session.flush()  # Get the ID
				count += 1

				# Save children with this section as parent
				for child in node.children:
					count += await save_tree(child, section.id)

			return count

		count = await save_tree(sections, None)
		await session.commit()
		logger.info(f"Saved {count} sections for document {document_id}")
		return count


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
	"""Get all sections for a document, ordered by position.

	Used for reconstructing the full document content.

	Args:
	    domain: Document domain
	    path: Document path

	Returns:
	    List of Section objects ordered by position
	"""
	async with AsyncSessionLocal() as session:
		# First find the document
		doc_result = await session.execute(
			select(Document).where(
				Document.domain == domain,
				Document.path == path,
			)
		)
		doc = doc_result.scalar_one_or_none()
		if not doc:
			return []

		# Get all sections ordered by position
		result = await session.execute(select(Section).where(Section.document_id == doc.id).order_by(Section.position))
		return list(result.scalars().all())


async def get_section_subtree_by_heading(
	domain: str,
	path: str,
	heading: str,
) -> list[Section]:
	"""Get a section and all its descendants by heading.

	Uses recursive CTE to traverse the parent_section_id tree.

	Args:
	    domain: Document domain
	    path: Document path
	    heading: Heading text to find

	Returns:
	    List of Section objects (the matching section + all descendants)
	"""
	async with AsyncSessionLocal() as session:
		# First find the document
		doc_result = await session.execute(
			select(Document).where(
				Document.domain == domain,
				Document.path == path,
			)
		)
		doc = doc_result.scalar_one_or_none()
		if not doc:
			return []

		# Use recursive CTE to get subtree
		sql = """
            WITH RECURSIVE subtree AS (
                SELECT * FROM sections
                WHERE document_id = :doc_id AND heading = :heading
                UNION ALL
                SELECT s.* FROM sections s
                JOIN subtree t ON s.parent_section_id = t.id
            )
            SELECT * FROM subtree ORDER BY position
        """
		result = await session.execute(
			text(sql),
			{"doc_id": str(doc.id), "heading": heading},
		)
		rows = result.fetchall()

		# Convert to Section objects
		return [
			Section(
				id=row.id,
				document_id=row.document_id,
				parent_section_id=row.parent_section_id,
				heading=row.heading,
				level=row.level,
				content=row.content,
				position=row.position,
			)
			for row in rows
		]


async def get_document_by_url(url: str) -> Optional[Document]:
	"""Retrieve a document by its URL.

	Args:
	    url: The full URL of the document

	Returns:
	    Document if found, None otherwise
	"""
	async with AsyncSessionLocal() as session:
		result = await session.execute(select(Document).where(Document.url == url))
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
	paths: list[str] | None = None,
	limit: int = 10,
) -> list[SearchResult]:
	"""Search sections using PostgreSQL full-text search.

	Uses websearch_to_tsquery() for natural language query parsing,
	ts_headline() for snippets, and recursive CTE for heading breadcrumbs.

	Args:
	    domain: Domain to search within (required)
	    query: Natural language search query
	    paths: Optional path prefixes to filter (e.g., ["/hooks"] matches "/hooks/useState")
	    limit: Maximum results to return

	Returns:
	    List of SearchResult objects ordered by relevance, with heading_path
	"""
	logger.debug(f"FTS search: domain={domain}, query={query}, paths={paths}")

	if not query.strip():
		return []

	async with AsyncSessionLocal() as session:
		# Build the SQL with heading_path via recursive CTE
		sql = """
            WITH RECURSIVE ancestors AS (
                -- Start with matching sections
                SELECT
                    s.id,
                    s.parent_section_id,
                    s.heading,
                    s.content,
                    s.document_id,
                    ts_rank(s.search_vector, websearch_to_tsquery('english', :query)) as rank,
                    ARRAY[s.heading] as path_array,
                    1 as depth
                FROM sections s
                JOIN documents d ON s.document_id = d.id
                WHERE d.domain = :domain
                  AND s.search_vector @@ websearch_to_tsquery('english', :query)
        """

		params: dict = {"domain": domain, "query": query, "limit": limit}

		# Add path prefix filtering if specified
		if paths:
			path_conditions = " OR ".join([f"d.path LIKE :path{i}" for i in range(len(paths))])
			sql += f" AND ({path_conditions})"
			for i, path in enumerate(paths):
				prefix = path if path.startswith("/") else f"/{path}"
				params[f"path{i}"] = f"{prefix}%"

		sql += """
                UNION ALL
                -- Recursively get ancestors
                SELECT
                    a.id,
                    p.parent_section_id,
                    p.heading,
                    a.content,
                    a.document_id,
                    a.rank,
                    p.heading || a.path_array,
                    a.depth + 1
                FROM ancestors a
                JOIN sections p ON a.parent_section_id = p.id
                WHERE a.depth < 10  -- Prevent infinite loops
            ),
            -- Get the full path for each original section
            full_paths AS (
                SELECT DISTINCT ON (id)
                    id,
                    content,
                    document_id,
                    rank,
                    path_array
                FROM ancestors
                ORDER BY id, depth DESC
            )
            SELECT
                d.url,
                d.path,
                ts_headline('english', fp.content, websearch_to_tsquery('english', :query),
                           'MaxWords=50, MinWords=20, StartSel=**, StopSel=**') as snippet,
                fp.rank,
                array_to_string(
                    array_remove(fp.path_array, NULL),
                    ' > '
                ) as heading_path
            FROM full_paths fp
            JOIN documents d ON fp.document_id = d.id
            ORDER BY fp.rank DESC
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


async def get_sections_for_toc(
	domain: str,
	path: str,
) -> list[tuple[UUID, UUID | None, str | None, int]]:
	"""Get section hierarchy data for building TOC.

	Returns minimal data needed to build a TOCEntry tree.

	Args:
	    domain: Document domain
	    path: Document path

	Returns:
	    List of tuples: (id, parent_section_id, heading, level)
	"""
	async with AsyncSessionLocal() as session:
		# Find the document
		doc_result = await session.execute(
			select(Document).where(
				Document.domain == domain,
				Document.path == path,
			)
		)
		doc = doc_result.scalar_one_or_none()
		if not doc:
			return []

		# Get section hierarchy data
		result = await session.execute(
			select(
				Section.id,
				Section.parent_section_id,
				Section.heading,
				Section.level,
			)
			.where(Section.document_id == doc.id)
			.order_by(Section.position)
		)
		return [(row.id, row.parent_section_id, row.heading, row.level) for row in result]
