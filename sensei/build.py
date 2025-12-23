"""Factory functions for building agent inputs and outputs."""

import logging

from pydantic_ai import RunContext

from sensei.database import storage
from sensei.deps import Deps
from sensei.settings import sensei_settings
from sensei.types import ToolError

logger = logging.getLogger(__name__)

# =============================================================================
# Response Building
# =============================================================================

FEEDBACK_TEMPLATE = """

---
**Help improve sensei:** Rate this response using `feedback` tool after trying it.

Query ID: `{query_id}`
"""


def build_response_with_feedback(output: str, query_id: str) -> str:
    """Append feedback instructions to agent output.

    Args:
        output: The agent's raw output
        query_id: The query ID for feedback submission

    Returns:
        Output with feedback template appended
    """
    return output + FEEDBACK_TEMPLATE.format(query_id=query_id)


def build_enhanced_query(
    query: str,
    language: str | None = None,
    library: str | None = None,
    version: str | None = None,
) -> str:
    """Build query with context metadata prepended.

    Args:
        query: The user's question
        language: Optional programming language
        library: Optional library/framework name
        version: Optional version specification

    Returns:
        Enhanced query with context prepended, or original query if no context
    """
    if not (language or library or version):
        return query

    context_parts = []
    if language:
        context_parts.append(f"Language: {language}")
    if library:
        context_parts.append(f"Library: {library}")
    if version:
        context_parts.append(f"Version: {version}")

    context_str = " | ".join(context_parts)
    return f"[Context: {context_str}]\n\n{query}"


async def build_deps(
    query: str,
    ctx: RunContext[Deps] | None = None,
) -> Deps:
    """Build deps for agent execution.

    Root query:  build_deps(query)
    Child query: build_deps(sub_question, ctx)

    Args:
        query: The query text (for cache lookup on root queries)
        ctx: Parent context. If provided, this is a child query.

    Raises:
        ToolError: If depth limit exceeded or missing parent context
    """
    if ctx is not None:
        # ─── Child Query ───
        if ctx.deps is None:
            raise ToolError("Cannot spawn sub-agent: missing deps in parent context")

        new_depth = ctx.deps.current_depth + 1
        if new_depth > sensei_settings.max_recursion_depth:
            raise ToolError(
                f"Cannot spawn sub-agent: depth limit exceeded ({new_depth}/{sensei_settings.max_recursion_depth})"
            )

        logger.debug(f"Building child deps: depth={new_depth}")
        return Deps(current_depth=new_depth)
    else:
        # ─── Root Query ───
        cache_hits = await storage.search_queries(query, limit=5)
        logger.debug(f"Building root deps: cache_hits={len(cache_hits)}")

        return Deps(cache_hits=cache_hits)
