"""Pydantic models for FastAPI request/response."""

from pydantic import BaseModel, Field


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


class QueryResponse(BaseModel):
	"""Response model for query results."""

	query_id: str = Field(
		...,
		description="Unique identifier for this query",
		json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
	)
	markdown: str = Field(
		...,
		description="Markdown documentation with code examples",
		json_schema_extra={"example": "# FastAPI OAuth\n\nHere's how to implement OAuth..."},
	)


class RatingRequest(BaseModel):
	"""Request model for rating a query response."""

	query_id: str = Field(
		...,
		description="The query ID to rate",
		json_schema_extra={"example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
	)
	correctness: int = Field(
		...,
		ge=1,
		le=5,
		description="Is the information/code correct? (1-5)",
		json_schema_extra={"example": 5},
	)
	relevance: int = Field(
		...,
		ge=1,
		le=5,
		description="Did it answer the question? (1-5)",
		json_schema_extra={"example": 5},
	)
	usefulness: int = Field(
		...,
		ge=1,
		le=5,
		description="Did it help solve the problem? (1-5)",
		json_schema_extra={"example": 5},
	)
	reasoning: str | None = Field(
		None,
		description="Why these ratings? What changed from last time?",
		json_schema_extra={"example": "Worked after applying, but token refresh was missing."},
	)
	agent_model: str | None = Field(
		None,
		description="Model identifier",
		json_schema_extra={"example": "claude-3-5-sonnet-20241022"},
	)
	agent_system: str | None = Field(
		None,
		description="Agent system name",
		json_schema_extra={"example": "Claude Code"},
	)
	agent_version: str | None = Field(
		None,
		description="Agent system version",
		json_schema_extra={"example": "2.1.0"},
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
