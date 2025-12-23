"""REST API server for Sensei.

Provides HTTP endpoints for non-MCP clients:
- POST /query - Query Sensei for documentation (saves to DB)
- POST /query/stream - Streaming query results as NDJSON (saves to DB)
- POST /api/chat - Vercel AI SDK streaming endpoint (lightweight, no DB save)
- POST /rate - Rate a query response
- GET /health - Health check
- /mcp/* - MCP server endpoint (unified: sensei, scout, kura, tome tools)

Usage:
    python -m sensei.api              # HTTP on port 8000
    python -m sensei.api -p 9000      # Custom port
"""

import sensei.sentry  # noqa: F401 - must be first to instrument FastAPI

import json
import sentry_sdk
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from pydantic_ai import messages, run
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from sensei import core
from sensei.agent import create_agent
from sensei.api.models import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    RatingRequest,
    RatingResponse,
)
from sensei.build import build_deps
from sensei.types import BrokenInvariant, ToolError, TransientError
from sensei.unified import mcp

logger = logging.getLogger(__name__)

# Rate limiter with in-memory storage (default)
limiter = Limiter(key_func=get_remote_address)

# Create MCP ASGI app for mounting (stateless to avoid session ID issues after restarts)
mcp_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Combined lifespan for FastAPI and MCP servers."""
    # MCP lifespan handles engine disposal via unified.py
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(
    title="Sensei REST API",
    description="HTTP API for Sensei documentation agent",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount MCP server at /mcp
app.mount("/mcp", mcp_app)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sensei.eightzerothree.co", "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """Query Sensei for documentation and code examples.

    Returns markdown documentation synthesized from multiple sources including
    Context7, Scout (GitHub repo exploration), and Tavily.

    Args:
        request: Query request with the user's question and optional filters

    Returns:
        Query response with unique ID and markdown documentation
    """
    logger.info(f"POST /query: {request.query[:100]}{'...' if len(request.query) > 100 else ''}")
    try:
        result = await core.handle_query(
            request.query,
            language=request.language,
            library=request.library,
            version=request.version,
        )
        logger.debug(f"Query successful: query_id={result.query_id}")
        return QueryResponse(query_id=result.query_id, output=result.output)
    except BrokenInvariant as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Service misconfigured: {e}")
        raise HTTPException(status_code=503, detail=f"{e}")
    except TransientError as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Service temporarily unavailable: {e}")
        raise HTTPException(status_code=503, detail=f"{e}")
    except ToolError as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Internal error: {e}")
        raise HTTPException(status_code=500, detail=f"{e}")
    except ModelHTTPError as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"{e}")


def _extract_prompt_from_vercel_body(body: bytes) -> str | None:
    """Extract user's last message from Vercel AI SDK v5 body.

    AI SDK v5 DefaultChatTransport sends: { id, messages: [...], trigger }
    Each message has: { id, role, parts: [{ type, text }] }
    """
    try:
        data = json.loads(body)
        for msg in reversed(data.get("messages", [])):
            if msg.get("role") == "user":
                for part in msg.get("parts", []):
                    if part.get("type") == "text":
                        text = part.get("text", "")
                        if text.strip():
                            return text
        return None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


@app.post("/api/chat")
@limiter.limit("3/minute")
async def chat(request: Request):
    """Vercel AI SDK-compatible chat endpoint (SSE).

    Lightweight streaming endpoint for the frontend demo.
    Does not save queries to DB (no feedback/caching).
    """
    body = await request.body()
    try:
        run_input = VercelAIAdapter.build_run_input(body)
    except ValidationError as e:
        return Response(
            content=e.json(),
            media_type="application/json",
            status_code=422,
        )

    # Extract prompt from documented Vercel format (not internal PydanticAI structures)
    prompt = _extract_prompt_from_vercel_body(body)
    if prompt is None:
        raise HTTPException(status_code=422, detail="Missing user text message in 'messages'")

    logger.info(f"POST /api/chat: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

    # Build deps with cache prefetch (root query, no ctx)
    deps = await build_deps(prompt)

    adapter = VercelAIAdapter(
        agent=create_agent(),
        run_input=run_input,
        accept=request.headers.get("accept"),
    )
    response = adapter.streaming_response(adapter.run_stream(deps=deps))
    response.headers.setdefault("Cache-Control", "no-cache")
    response.headers.setdefault("Connection", "keep-alive")
    response.headers.setdefault("X-Accel-Buffering", "no")
    return response


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _stream_ndjson(data: dict) -> bytes:
    return json.dumps(data, default=_json_default).encode("utf-8") + b"\n"


@app.post("/query/stream")
async def query_stream(request: QueryRequest):
    """Stream query results as NDJSON.

    Returns real-time events as agent executes:
    - Tool calls (with name and arguments)
    - Tool results (success or error)
    - Thinking blocks (reasoning, if enabled)
    - Final response (complete markdown)

    Args:
        request: Query request with the user's question and optional filters

    Returns:
        NDJSON stream of agent execution events
    """
    logger.info(f"POST /query/stream: {request.query[:100]}{'...' if len(request.query) > 100 else ''}")

    async def event_generator():
        try:
            async for event in core.stream_query(
                request.query,
                language=request.language,
                library=request.library,
                version=request.version,
            ):
                event_type = type(event).__name__
                logger.debug(f"Stream event: {event_type}")

                if isinstance(event, run.AgentRunResultEvent):
                    yield _stream_ndjson(
                        {
                            "event_type": "agent_run_result",
                            "output": event.result.output,
                        }
                    )
                elif isinstance(
                    event,
                    (
                        messages.PartStartEvent,
                        messages.PartDeltaEvent,
                        messages.PartEndEvent,
                        messages.FunctionToolCallEvent,
                        messages.FunctionToolResultEvent,
                        messages.FinalResultEvent,
                    ),
                ):
                    # Known event types - serialize with event_kind
                    yield _stream_ndjson(
                        {
                            "event_type": event_type,
                            "event_kind": event.event_kind,
                            **asdict(event),
                        }
                    )
                else:
                    # Unknown event - log and pass through what we can
                    logger.warning(f"Unknown event type: {event_type}")
                    yield _stream_ndjson(
                        {
                            "event_type": event_type,
                            "raw": str(event),
                        }
                    )
        except ModelHTTPError as e:
            sentry_sdk.capture_exception(e)
            logger.error(f"Stream error: {e}")
            yield _stream_ndjson(
                {
                    "error": e.__class__.__name__,
                    "model_http_error": {
                        "model_name": e.model_name,
                        "status_code": e.status_code,
                        "body": e.body,
                    },
                }
            )

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.post("/rate", response_model=RatingResponse)
async def rate(request: RatingRequest) -> RatingResponse:
    """Rate a Sensei query response.

    Stores user feedback for future improvements and optimization.

    Args:
        request: Rating request with query ID, rating, and optional feedback

    Returns:
        Confirmation that the rating was recorded
    """
    logger.info(f"POST /rate: query_id={request.query_id}")
    try:
        # RatingRequest inherits from Rating, so we can pass it directly
        await core.handle_rating(request)
        logger.debug(f"Rating saved for query_id={request.query_id}")
        return RatingResponse(status="recorded")
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error(f"Failed to save rating: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save rating: {e}")


@app.get("/")
async def root() -> dict:
    """Root endpoint for deployment health checks."""
    return {}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns the health status of the service.

    Returns:
        Health status response
    """
    return HealthResponse(status="healthy")


@app.get("/opencode")
async def opencode_installer() -> FileResponse:
    """Installer script for the Sensei OpenCode plugin/tools."""
    candidates = [
        _REPO_ROOT / "packages" / "sensei-opencode" / "dist" / "install.sh",
        _REPO_ROOT / "packages" / "sensei-opencode" / "src" / "install.sh",
    ]
    for path in candidates:
        if path.exists():
            return FileResponse(
                path=path,
                media_type="text/plain; charset=utf-8",
                filename="sensei-opencode-install.sh",
            )
    raise HTTPException(status_code=404, detail="OpenCode installer not found")


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={"detail": "Not found"},
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Custom 500 handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
