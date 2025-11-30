"""Pydantic models for FastAPI request/response."""

from pydantic import BaseModel, ConfigDict, Field

from sensei.types import QueryResult, Rating


class QueryRequest(BaseModel):
	"""Request model for querying Sensei."""

	query: str = Field(
		...,
		min_length=1,
		description="The question or problem to solve",
		json_schema_extra={"example": "How do I authenticate with OAuth in FastAPI?"},
	)
	language: str | None = Field(
		None,
		description="Programming language (e.g., 'python', 'typescript', 'go')",
		json_schema_extra={"example": "python"},
	)
	library: str | None = Field(
		None,
		description="Library or framework name (e.g., 'fastapi', 'react', 'sqlalchemy')",
		json_schema_extra={"example": "fastapi"},
	)
	version: str | None = Field(
		None,
		description="Version specification (any valid semver, e.g., '>=3.0', '2.1.0', 'v14.2')",
		json_schema_extra={"example": ">=0.100.0"},
	)


class QueryResponse(QueryResult):
	"""Response model for query results."""

	model_config = ConfigDict(
		json_schema_extra={
			"example": {
				"query_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				"markdown": "# FastAPI OAuth\n\nHere's how to implement OAuth...",
			}
		}
	)


class RatingRequest(Rating):
	"""Request model for rating a query response."""

	model_config = ConfigDict(
		json_schema_extra={
			"example": {
				"query_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
				"correctness": 5,
				"relevance": 5,
				"usefulness": 5,
				"reasoning": "Worked after applying, but token refresh was missing.",
				"agent_model": "claude-3-5-sonnet-20241022",
				"agent_system": "Claude Code",
				"agent_version": "2.1.0",
			}
		}
	)


class RatingResponse(BaseModel):
	"""Response model for rating submission."""

	status: str = Field(
		...,
		description="Status of the rating submission",
		json_schema_extra={"example": "recorded"},
	)


class HealthResponse(BaseModel):
	"""Response model for health check."""

	status: str = Field(
		...,
		description="Health status of the service",
		json_schema_extra={"example": "healthy"},
	)
