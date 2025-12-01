"""Core cache functions for Kura.

These are the underlying functions that power the MCP tools.
They connect to the same PostgreSQL database as the main Sensei app.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sensei.database import storage
from sensei.database.models import Query
from sensei.types import NoResults, Success

logger = logging.getLogger(__name__)


def _compute_age_days(inserted_at: datetime | str | None) -> int:
    """Compute age in days from inserted_at timestamp.

    Args:
        inserted_at: Timezone-aware datetime from DB, or ISO string from JSON.
                     DB uses DateTime(timezone=True), so datetimes are always aware.

    Returns:
        Number of days since the timestamp (0 if None or today).
    """
    if inserted_at is None:
        return 0
    if isinstance(inserted_at, str):
        inserted_at = datetime.fromisoformat(inserted_at.replace("Z", "+00:00"))
    return (datetime.now(UTC) - inserted_at).days


def format_query_response(query: Query) -> str:
    """Format a Query model to markdown for display.

    Computes derived values (age) at the display edge.
    """
    age_days = _compute_age_days(query.inserted_at)

    return "\n".join(
        [
            f"# Cached Response: {query.id}",
            "",
            f"**Age:** {age_days} days",
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
    limit: int = 10,
) -> Success[str] | NoResults:
    """Search cached queries for relevant past answers.

    Use this to find previously answered questions that might help with the current query.

    Args:
        search_term: Keywords to search for in cached queries
        limit: Maximum number of results (default 10)

    Returns:
        Formatted list of cache hits with query_id, truncated query, and age
    """
    logger.info(f"Searching cache: term={search_term}")

    hits = await storage.search_queries(search_term, limit=limit)

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


async def get_cached_response(query_id: UUID) -> Success[str] | NoResults:
    """Retrieve a full cached response by query ID.

    Use this after finding relevant cache hits with search_cache.

    Args:
        query_id: The UUID of the cached query to retrieve

    Returns:
        Full cached query and response with metadata
    """
    logger.info(f"Getting cached response: query_id={query_id}")

    query = await storage.get_query(query_id)
    if not query:
        return NoResults()

    return Success(format_query_response(query))
