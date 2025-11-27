"""Database operations for Sensei using SQLAlchemy with async support."""

import json
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sensei.config import settings
from sensei.database.models import Base, Query
from sensei.database.models import Rating as RatingModel
from sensei.types import CacheHit, Rating

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
	settings.database_url,
	echo=False,
	future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
	engine,
	class_=AsyncSession,
	expire_on_commit=False,
)


async def init_db() -> None:
	"""Initialize database by creating all tables and FTS5 index."""
	logger.debug(f"Initializing database: {settings.database_url}")
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)
		# Create FTS5 virtual table for query search
		await conn.execute(
			text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS queries_fts USING fts5(
                    query,
                    content=queries,
                    content_rowid=rowid
                )
            """)
		)
		# Triggers to keep FTS5 in sync
		await conn.execute(
			text("""
                CREATE TRIGGER IF NOT EXISTS queries_insert AFTER INSERT ON queries BEGIN
                    INSERT INTO queries_fts(rowid, query) VALUES (new.rowid, new.query);
                END
            """)
		)
		await conn.execute(
			text("""
                CREATE TRIGGER IF NOT EXISTS queries_delete AFTER DELETE ON queries BEGIN
                    INSERT INTO queries_fts(queries_fts, rowid, query) VALUES ('delete', old.rowid, old.query);
                END
            """)
		)
		await conn.execute(
			text("""
                CREATE TRIGGER IF NOT EXISTS queries_update AFTER UPDATE ON queries BEGIN
                    INSERT INTO queries_fts(queries_fts, rowid, query) VALUES ('delete', old.rowid, old.query);
                    INSERT INTO queries_fts(rowid, query) VALUES (new.rowid, new.query);
                END
            """)
		)
	logger.info("Database initialized successfully (with FTS5)")


async def save_query(
	query_id: str,
	query: str,
	output: str,
	messages: bytes | None = None,
	sources_used: Optional[list[str]] = None,
	language: Optional[str] = None,
	library: Optional[str] = None,
	version: Optional[str] = None,
	parent_query_id: Optional[str] = None,
	depth: int = 0,
) -> None:
	"""Save a query and its response to the database.

	Args:
	    query_id: Unique identifier for the query
	    query: The user's query string
	    output: The final text output from the agent
	    messages: JSON bytes of all intermediate messages (from result.new_messages_json())
	    sources_used: Optional list of source names that were queried
	    language: Optional programming language filter
	    library: Optional library/framework name
	    version: Optional version specification
	    parent_query_id: Optional parent query ID for sub-queries
	    depth: Recursion depth (0 = top-level)
	"""
	logger.info(f"Saving query to database: query_id={query_id}, parent={parent_query_id}, depth={depth}")
	async with AsyncSessionLocal() as session:
		query_record = Query(
			query_id=query_id,
			query=query,
			language=language,
			library=library,
			version=version,
			output=output,
			messages=messages.decode("utf-8") if messages else None,
			sources_used=json.dumps(sources_used) if sources_used else None,
			parent_query_id=parent_query_id,
			depth=depth,
		)
		session.add(query_record)
		await session.commit()
	logger.debug(f"Query saved: query_id={query_id}, depth={depth}")


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


async def get_query(query_id: str) -> Optional[Query]:
	"""Retrieve a query by its ID.

	Args:
	    query_id: The query ID to retrieve

	Returns:
	    Query object if found, None otherwise
	"""
	async with AsyncSessionLocal() as session:
		result = await session.execute(select(Query).where(Query.query_id == query_id))
		return result.scalar_one_or_none()


async def search_queries_fts(
	search_term: str,
	library: Optional[str] = None,
	version: Optional[str] = None,
	limit: int = 10,
) -> list[CacheHit]:
	"""Search cached queries using FTS5.

	Args:
	    search_term: The search term for full-text search
	    library: Optional library filter
	    version: Optional version filter
	    limit: Maximum results to return

	Returns:
	    List of CacheHit objects sorted by relevance
	"""
	from datetime import UTC, datetime

	logger.debug(f"FTS search: term={search_term}, library={library}, version={version}")

	async with AsyncSessionLocal() as session:
		# Build query with optional filters
		sql = """
            SELECT q.query_id, q.query, q.library, q.version, q.created_at
            FROM queries q
            WHERE q.rowid IN (
                SELECT rowid FROM queries_fts WHERE queries_fts MATCH :search_term
            )
        """
		params: dict = {"search_term": search_term}

		if library:
			sql += " AND q.library = :library"
			params["library"] = library
		if version:
			sql += " AND q.version = :version"
			params["version"] = version

		sql += " LIMIT :limit"
		params["limit"] = limit

		result = await session.execute(text(sql), params)
		rows = result.fetchall()

		now = datetime.now(UTC)
		hits = []
		for row in rows:
			query_id, query_text, lib, ver, created_at = row
			# Parse datetime if it's a string (from raw SQL)
			if isinstance(created_at, str):
				created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
			if created_at and created_at.tzinfo is None:
				created_at = created_at.replace(tzinfo=UTC)
			age_days = (now - created_at).days if created_at else 0
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
