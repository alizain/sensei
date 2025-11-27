"""Core orchestration logic shared by API and MCP layers."""

import logging
import uuid
from typing import AsyncIterator

from pydantic_ai import AgentRunResultEvent, AgentStreamEvent

from sensei import deps as deps_module
from sensei.agent import agent
from sensei.database import storage
from sensei.database.storage import search_queries_fts
from sensei.tools.exec_plan import clear_plan
from sensei.types import QueryResult, Rating

logger = logging.getLogger(__name__)

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
	logger.info("=== CORE.STREAM_QUERY ENTERED ===")
	query_id = str(uuid.uuid4())

	logger.info(f"Streaming query: query_id={query_id}, language={language}, library={library}, version={version}")
	logger.debug(f"Query text: {query[:200]}{'...' if len(query) > 200 else ''}")

	# Build enhanced query with context
	enhanced_query = _build_enhanced_query(query, language, library, version)
	if language or library or version:
		logger.debug("Enhanced query with context")

	# Prefetch cache hits (no library/version filter - let agent decide relevance)
	cache_hits = await search_queries_fts(query, limit=5)
	logger.debug(f"Prefetched {len(cache_hits)} cache hits")

	# Call agent's streaming API
	deps = deps_module.Deps(query_id=query_id, cache_hits=cache_hits)
	try:
		logger.debug(f"Starting agent stream with query_id={query_id}")
		async for event in agent.run_stream_events(enhanced_query, deps=deps):
			yield event  # Pass through all events

			# Save to DB when agent completes
			if isinstance(event, AgentRunResultEvent):
				output = event.result.output
				logger.info(f"Agent completed successfully: {len(output)} chars")

				await storage.save_query(
					query_id=query_id,
					query=query,
					output=output,
					messages=event.result.new_messages_json(),
					sources_used=None,
					language=language,
					library=library,
					version=version,
				)
				logger.info(f"Query saved to database: query_id={query_id}")
	finally:
		clear_plan(query_id)


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
	logger.info("=== CORE.HANDLE_QUERY ENTERED ===")
	query_id = str(uuid.uuid4())

	logger.info(f"Processing query: query_id={query_id}, language={language}, library={library}, version={version}")
	logger.debug(f"Query text: {query[:200]}{'...' if len(query) > 200 else ''}")

	# Build enhanced query with context
	enhanced_query = _build_enhanced_query(query, language, library, version)
	if language or library or version:
		logger.debug("Enhanced query with context")

	# Prefetch cache hits (no library/version filter - let agent decide relevance)
	cache_hits = await search_queries_fts(query, limit=5)
	logger.debug(f"Prefetched {len(cache_hits)} cache hits")

	# Call agent directly - orchestration happens here in core
	deps = deps_module.Deps(query_id=query_id, cache_hits=cache_hits)
	try:
		logger.debug(f"Running agent with query_id={query_id}")
		result = await agent.run(enhanced_query, deps=deps)
		output = result.output
		logger.info(f"Agent completed successfully: {len(output)} chars")

		await storage.save_query(
			query_id=query_id,
			query=query,
			output=output,
			messages=result.new_messages_json(),
			sources_used=None,
			language=language,
			library=library,
			version=version,
		)
		logger.info(f"Query saved to database: query_id={query_id}")
	finally:
		clear_plan(query_id)

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
