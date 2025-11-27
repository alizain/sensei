"""Cache tools for Sensei."""

import json
import logging
from datetime import UTC, datetime
from typing import Optional

from sensei.database import storage
from sensei.database.models import Query
from sensei.types import NoResults, Success

logger = logging.getLogger(__name__)


def _compute_age_days(created_at: datetime | str | None) -> int:
	"""Compute age in days from created_at timestamp.

	Handles datetime coercion at the display edge.
	"""
	if created_at is None:
		return 0
	if isinstance(created_at, str):
		created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
	if created_at.tzinfo is None:
		created_at = created_at.replace(tzinfo=UTC)
	return (datetime.now(UTC) - created_at).days


def format_query_response(query: Query) -> str:
	"""Format a Query model to markdown for display.

	Computes derived values (age, parsed sources) at the display edge.
	"""
	age_days = _compute_age_days(query.created_at)
	sources = json.loads(query.sources_used) if query.sources_used else []
	sources_str = ", ".join(sources) if sources else "none recorded"

	return "\n".join(
		[
			f"# Cached Response: {query.query_id}",
			"",
			f"**Age:** {age_days} days",
			f"**Sources:** {sources_str}",
			"",
			"## Original Query",
			"",
			query.query,
			"",
			"## Cached Response",
			"",
			query.output,
		]
	)


async def search_cache(
	search_term: str,
	library: Optional[str] = None,
	version: Optional[str] = None,
	limit: int = 10,
) -> Success[str] | NoResults:
	"""Search cached queries for relevant past answers.

	Use this to find previously answered questions that might help with the current query.

	Args:
	    search_term: Keywords to search for in cached queries
	    library: Optional library name to filter results
	    version: Optional version to filter results
	    limit: Maximum number of results (default 10)

	Returns:
	    Formatted list of cache hits with query_id, truncated query, and age
	"""
	logger.info(f"Searching cache: term={search_term}, library={library}")

	hits = await storage.search_queries_fts(search_term, library=library, version=version, limit=limit)

	if not hits:
		return NoResults()

	lines = ["# Cache Search Results\n"]
	for hit in hits:
		age_str = f"{hit.age_days} days ago" if hit.age_days > 0 else "today"
		lib_str = f" [{hit.library}]" if hit.library else ""
		ver_str = f" v{hit.version}" if hit.version else ""
		lines.append(f"- **{hit.query_id}**{lib_str}{ver_str} ({age_str})")
		lines.append(f"  {hit.query_truncated}")
		lines.append("")

	return Success("\n".join(lines))


async def get_cached_response(query_id: str) -> Success[str] | NoResults:
	"""Retrieve a full cached response by query ID.

	Use this after finding relevant cache hits with search_cache.

	Args:
	    query_id: The ID of the cached query to retrieve

	Returns:
	    Full cached query and response with metadata
	"""
	logger.info(f"Getting cached response: query_id={query_id}")

	query = await storage.get_query(query_id)
	if not query:
		return NoResults()

	return Success(format_query_response(query))
