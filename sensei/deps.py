"""Shared dependency container for Sensei tools and agent."""

from typing import Optional
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from sensei.config import settings
from sensei.types import CacheHit


class Deps(BaseModel):
	"""Dependency container passed to tools."""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	http_client: httpx.AsyncClient | None = None
	query_id: UUID | None = None
	# Sub-sensei context
	parent_id: UUID | None = None
	current_depth: int = 0
	max_depth: int = settings.max_recursion_depth
	# Prefetched cache hits
	cache_hits: list[CacheHit] = Field(default_factory=list)
	# ExecPlan for this request (request-scoped, no global state)
	exec_plan: Optional[str] = None
