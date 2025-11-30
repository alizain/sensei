"""FastAPI server for Sensei."""

import json
import logging
from dataclasses import asdict
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic_ai import messages, run
from pydantic_ai.exceptions import ModelHTTPError

from sensei import core
from sensei.server.models import (
	HealthResponse,
	QueryRequest,
	QueryResponse,
	RatingRequest,
	RatingResponse,
)
from sensei.types import BrokenInvariant, ToolError, TransientError

logger = logging.getLogger(__name__)

api_app = FastAPI(
	title="Sensei API",
	description="HTTP API endpoints",
)


@api_app.post("/query", response_model=QueryResponse)
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
		return QueryResponse(query_id=result.query_id, markdown=result.markdown)
	except BrokenInvariant as e:
		logger.error(f"Service misconfigured: {e}")
		raise HTTPException(status_code=503, detail=f"{e}")
	except TransientError as e:
		logger.error(f"Service temporarily unavailable: {e}")
		raise HTTPException(status_code=503, detail=f"{e}")
	except ToolError as e:
		logger.error(f"Internal error: {e}")
		raise HTTPException(status_code=500, detail=f"{e}")
	except ModelHTTPError as e:
		logger.error(f"Unexpected error: {e}")
		raise HTTPException(status_code=500, detail=f"{e}")


def _json_default(obj):
	if isinstance(obj, datetime):
		return obj.isoformat()
	return obj


def _stream_ndjson(data: dict) -> bytes:
	return json.dumps(data, default=_json_default).encode("utf-8") + b"\n"


@api_app.post("/query/stream")
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


@api_app.post("/rate", response_model=RatingResponse)
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
		logger.error(f"Failed to save rating: {e}", exc_info=True)
		raise HTTPException(status_code=500, detail=f"Failed to save rating: {e}")


@api_app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
	"""Health check endpoint.

	Returns the health status of the service.

	Returns:
	    Health status response
	"""
	return HealthResponse(status="healthy")


@api_app.exception_handler(404)
async def not_found_handler(request, exc):
	"""Custom 404 handler."""
	return JSONResponse(
		status_code=404,
		content={"detail": "Not found"},
	)


@api_app.exception_handler(500)
async def internal_error_handler(request, exc):
	"""Custom 500 handler."""
	return JSONResponse(
		status_code=500,
		content={"detail": "Internal server error"},
	)
