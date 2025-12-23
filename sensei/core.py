"""Core orchestration logic shared by API and MCP layers."""

import json
import logging
from typing import AsyncIterator

from pydantic_ai import AgentRunResultEvent, AgentStreamEvent

from sensei.agent import create_agent
from sensei.build import build_deps, build_enhanced_query, build_response_with_feedback
from sensei.database import storage
from sensei.types import QueryResult, Rating

logger = logging.getLogger(__name__)


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

    enhanced_query = build_enhanced_query(query, language, library, version)
    deps = await build_deps(query)

    agent = create_agent()
    async for event in agent.run_stream_events(enhanced_query, deps=deps):
        yield event

        if isinstance(event, AgentRunResultEvent):
            output = event.result.output
            logger.info(f"Agent completed: {len(output)} chars")
            messages = json.loads(event.result.new_messages_json())
            await storage.save_query(
                query=query,
                output=output,
                messages=messages,
                language=language,
                library=library,
                version=version,
            )


async def handle_query(
    query: str,
    language: str | None = None,
    library: str | None = None,
    version: str | None = None,
) -> QueryResult:
    """Execute a query and return the result.

    Uses streaming internally to avoid Anthropic SDK timeout errors
    with high max_tokens values (required for extended thinking).

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

    enhanced_query = build_enhanced_query(query, language, library, version)
    deps = await build_deps(query)

    # Use streaming to avoid "Streaming is required for operations that may
    # take longer than 10 minutes" error from Anthropic SDK with high max_tokens
    agent = create_agent()
    output = ""
    messages = []
    async for event in agent.run_stream_events(enhanced_query, deps=deps):
        if isinstance(event, AgentRunResultEvent):
            output = event.result.output
            messages = json.loads(event.result.new_messages_json())

    logger.info(f"Agent completed: {len(output)} chars")
    query_id = await storage.save_query(
        query=query,
        output=output,
        messages=messages,
        language=language,
        library=library,
        version=version,
    )

    output_with_feedback = build_response_with_feedback(output, str(query_id))
    return QueryResult(query_id=query_id, output=output_with_feedback)


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
