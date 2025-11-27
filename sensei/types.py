"""Type definitions for Sensei.

This module contains:
- Exception hierarchy for structured error handling
- Result types for tool return values
- Domain models shared across layers
"""

from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

# =============================================================================
# Exceptions
# =============================================================================


class SenseiError(Exception):
	"""Base for all Sensei errors."""

	pass


class BrokenInvariant(SenseiError):
	"""Setup/config error - cannot continue (e.g., missing API key)."""

	pass


class TransientError(SenseiError):
	"""Temporary failure - retry may succeed (e.g., network timeout)."""

	pass


class ToolError(SenseiError):
	"""Tool failed - try a different approach."""

	pass


# =============================================================================
# Result Types
# =============================================================================

T = TypeVar("T")


@dataclass
class Success(Generic[T]):
	"""Tool returned data successfully."""

	data: T


@dataclass
class NoResults:
	"""Tool executed successfully but found no results."""

	pass


# =============================================================================
# Domain Models
# =============================================================================


class QueryResult(BaseModel):
	"""Result of a query operation."""

	query_id: str
	markdown: str


class Rating(BaseModel):
	"""Rating for a query response."""

	query_id: str = Field(..., description="The query ID to rate")
	correctness: int = Field(..., ge=1, le=5)
	relevance: int = Field(..., ge=1, le=5)
	usefulness: int = Field(..., ge=1, le=5)
	reasoning: str | None = None
	agent_model: str | None = None
	agent_system: str | None = None
	agent_version: str | None = None


class CacheHit(BaseModel):
	"""A cache search result summary."""

	query_id: str
	query_truncated: str = Field(..., description="First 100 chars of query")
	age_days: int
	library: str | None = None
	version: str | None = None


class SubSenseiResult(BaseModel):
	"""Result from spawning a sub-sensei."""

	query_id: str
	response_markdown: str
	from_cache: bool
	age_days: int | None = None
