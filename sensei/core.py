"""Core orchestration logic shared by API and MCP layers."""

import logging
from typing import AsyncIterator

from pydantic_ai import AgentRunResultEvent, AgentStreamEvent

from sensei import deps as deps_module
from sensei.agent import agent
from sensei.database import storage
from sensei.types import QueryResult, Rating

logger = logging.getLogger(__name__)

# =============================================================================
# Shared Helpers
# =============================================================================


async def _prepare_query(
	query: str,
	language: str | None = None,
	library: str | None = None,
	version: str | None = None,
) -> tuple[str, deps_module.Deps]:
	"""Prepare enhanced query and deps for agent execution.

	Args:
	    query: The user's question
	    language: Optional programming language
	    library: Optional library/framework name
	    version: Optional version specification

	Returns:
	    Tuple of (enhanced_query, deps with cache hits)
	"""
	enhanced_query = _build_enhanced_query(query, language, library, version)
	if language or library or version:
		logger.debug("Enhanced query with context")

	cache_hits = await storage.search_queries(query, limit=5)
	logger.debug(f"Prefetched {len(cache_hits)} cache hits")

	deps = deps_module.Deps(cache_hits=cache_hits)
	return enhanced_query, deps


async def _save_query_result(
	query: str,
	output: str,
	messages_json: bytes,
	language: str | None = None,
	library: str | None = None,
	version: str | None = None,
) -> str:
	"""Save query result to storage.

	Args:
	    query: Original query text
	    output: Agent output
	    messages_json: Serialized message history
	    language: Optional programming language
	    library: Optional library/framework name
	    version: Optional version specification

	Returns:
	    The generated query_id
	"""
	query_id = await storage.save_query(
		query=query,
		output=output,
		messages=messages_json,
		language=language,
		library=library,
		version=version,
	)
	logger.info(f"Query saved to database: id={query_id}")
	return query_id


# =============================================================================
# Constants
# =============================================================================

FEEDBACK_TEMPLATE = """

---
**Help improve sensei:** Rate this response using `feedback` tool after trying it.

Query ID: `{query_id}`
"""


def _build_enhanced_query(
	query: str,
	language: str | None,
	library: str | None,
	version: str | None,
) -> str:
	"""Build query with context metadata.

	Args:
	    query: The user's question
	    language: Optional programming language
	    library: Optional library/framework name
	    version: Optional version specification

	Returns:
	    Enhanced query with context prepended
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


async def stream_query(
	query: str,
	language: str | None = None,
	library: str | None = None,
	version: str | None = None,
) -> AsyncIterator[AgentStreamEvent]:
	"""Stream query execution events (raw PydanticAI events).

	Args:
	    query: The user's question or problem to solve
	    language: Optional programming language filter
	    library: Optional library/framework name
	    version: Optional version specification

	Yields:
	    AgentStreamEvent instances (FunctionToolCallEvent,
	    FunctionToolResultEvent, AgentRunResultEvent, etc.)

	Raises:
	    BrokenInvariant: If configuration is invalid
	    TransientError: If external services are temporarily unavailable
	    ToolError: If the agent fails to process the query
	"""
	logger.info(f"Streaming query: language={language}, library={library}, version={version}")
	logger.debug(f"Query text: {query[:200]}{'...' if len(query) > 200 else ''}")

	enhanced_query, deps = await _prepare_query(query, language, library, version)

	async for event in agent.run_stream_events(enhanced_query, deps=deps):
		yield event

		if isinstance(event, AgentRunResultEvent):
			output = event.result.output
			logger.info(f"Agent completed successfully: {len(output)} chars")
			await _save_query_result(
				query,
				output,
				event.result.new_messages_json(),
				language,
				library,
				version,
			)


async def handle_query(
	query: str,
	language: str | None = None,
	library: str | None = None,
	version: str | None = None,
) -> QueryResult:
	"""Execute a query and return the result.

	Args:
	    query: The user's question or problem to solve
	    language: Optional programming language filter
	    library: Optional library/framework name
	    version: Optional version specification

	Raises:
	    BrokenInvariant: If configuration is invalid
	    TransientError: If external services are temporarily unavailable
	    ToolError: If the agent fails to process the query
	"""
	logger.info(f"Processing query: language={language}, library={library}, version={version}")
	logger.debug(f"Query text: {query[:200]}{'...' if len(query) > 200 else ''}")

	enhanced_query, deps = await _prepare_query(query, language, library, version)

	result = await agent.run(enhanced_query, deps=deps)
	output = result.output
	logger.info(f"Agent completed successfully: {len(output)} chars")

	query_id = await _save_query_result(
		query,
		output,
		result.new_messages_json(),
		language,
		library,
		version,
	)

	output_with_feedback = output + FEEDBACK_TEMPLATE.format(query_id=query_id)
	return QueryResult(query_id=query_id, markdown=output_with_feedback)


async def handle_rating(rating: Rating) -> None:
	"""Record a rating for a query response.

	Raises:
	    ToolError: If the rating cannot be saved
	"""
	logger.info(
		f"Processing rating: query_id={rating.query_id}, correctness={rating.correctness}, relevance={rating.relevance}, usefulness={rating.usefulness}"
	)
	await storage.save_rating(rating)
	logger.debug(f"Rating saved to database: query_id={rating.query_id}")
