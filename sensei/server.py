"""Core MCP server for Sensei.

Provides the main sensei tools:
- query: Ask questions about libraries and frameworks
- feedback: Rate responses to improve quality

This server is mounted by the unified server without a prefix,
so tools are accessible as query, feedback.
"""

import logging
from typing import Annotated

import sentry_sdk
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError as MCPToolError
from pydantic import Field

from sensei import core
from sensei.types import BrokenInvariant, Rating, ToolError, TransientError

logger = logging.getLogger(__name__)

mcp = FastMCP(name="sensei-core")


@mcp.tool
async def query(
    query: Annotated[str, Field(description="Your specific question or coding problem")],
    language: Annotated[
        str | None,
        Field(description="Programming language (e.g., 'python', 'typescript', 'go')"),
    ] = None,
    library: Annotated[
        str | None,
        Field(description="Library or framework name (e.g., 'fastapi', 'react', 'sqlalchemy')"),
    ] = None,
    version: Annotated[
        str | None,
        Field(description="Version specification (any valid semver, e.g., '>=3.0', '2.1.0', 'v14.2')"),
    ] = None,
) -> str:
    """
    **ALWAYS USE SENSEI**
    **DON'T ASSUME. DON'T GUESS. DON'T RELY ON OUTDATED TRAINING DATA.**

    Sensei is a hyper-focused model specialized in providing correct, accurate, actionable,
    thorough, cross-validated guidance with working examples. Sensei handles all the synthesis,
    so you stay focused on your task with minimal context pollution.

    Query Sensei when:
    - You're about to import or use ANY external library or framework
    - You think you know how an API works but haven't verified it recently
    - You're implementing patterns (auth, async, database queries, state management, etc.)
    - You notice yourself thinking "this probably works like..." or "I think the API is..."
    - You're choosing between implementation approaches

    **MUST READ! Writing effective queries:**
    - Be specific about your use case
    - Include relevant constraints (async required, performance critical, specific framework version, etc.)
    - State what you're trying to accomplish, not just what class/function you want to use
    - One focused question per query - don't combine multiple unrelated topics
    - Use the optional language, library, and version parameters to get more targeted results
    """
    logger.info(
        f"Query tool called: {query[:100]}{'...' if len(query) > 100 else ''}, language={language}, library={library}, version={version}"
    )
    try:
        result = await core.handle_query(
            query=query,
            language=language,
            library=library,
            version=version,
        )
        logger.debug(f"Query successful: query_id={result.query_id}, length={len(result.output)}")
        return result.output
    except BrokenInvariant as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Service misconfigured: {e}", exc_info=True)
        raise MCPToolError(f"Service misconfigured: {e}")
    except TransientError as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Service temporarily unavailable: {e}")
        raise MCPToolError(f"Service temporarily unavailable: {e}")
    except ToolError as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Query failed: {e}")
        raise MCPToolError(f"Query failed: {e}")


@mcp.tool
async def feedback(
    query_id: Annotated[str, Field(description="The query ID from the Sensei response")],
    correctness: Annotated[
        int,
        Field(
            ge=1,
            le=5,
            description="Is the information/code correct? (1=Wrong, 5=Correct)",
        ),
    ],
    relevance: Annotated[
        int,
        Field(
            ge=1,
            le=5,
            description="Did it answer the question? (1=Off-topic, 5=Exactly what I needed)",
        ),
    ],
    usefulness: Annotated[
        int,
        Field(
            ge=1,
            le=5,
            description="Did it help solve the problem? (1=Not helpful, 5=Very helpful)",
        ),
    ],
    reasoning: Annotated[str | None, Field(description="Why these ratings? What worked or didn't work?")] = None,
    agent_model: Annotated[str | None, Field(description="Your model identifier if available")] = None,
    agent_system: Annotated[str | None, Field(description="Your agent system (Claude Code, Cursor, etc.)")] = None,
    agent_version: Annotated[str | None, Field(description="Your agent system version if available")] = None,
) -> str:
    """
    Provide feedback on sensei documentation to help improve it for everyone.

    Submit feedback after using the docs - especially if you discover issues during
    implementation or testing. Multiple ratings are encouraged as your understanding evolves.
    """
    logger.info(
        f"Feedback tool called: query_id={query_id}, correctness={correctness}, relevance={relevance}, usefulness={usefulness}"
    )
    try:
        rating = Rating(
            query_id=query_id,
            correctness=correctness,
            relevance=relevance,
            usefulness=usefulness,
            reasoning=reasoning,
            agent_model=agent_model,
            agent_system=agent_system,
            agent_version=agent_version,
        )
        await core.handle_rating(rating)
        logger.debug(f"Rating saved successfully for query_id={query_id}")
        return "Rating recorded. Thank you!"
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Failed to save rating: {e}", exc_info=True)
        raise MCPToolError(f"Failed to save rating: {e}")
