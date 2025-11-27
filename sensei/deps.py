"""Shared dependency container for Sensei tools and agent."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from sensei.config import settings
from sensei.types import CacheHit


class Deps(BaseModel):
	"""Dependency container passed to tools."""

	model_config = ConfigDict(arbitrary_types_allowed=True)

	http_client: Optional[Any] = None
	query_id: Optional[str] = None
	# Sub-sensei context
	parent_query_id: Optional[str] = None
	current_depth: int = 0
	max_depth: int = settings.max_recursion_depth
	# Prefetched cache hits
	cache_hits: list[CacheHit] = Field(default_factory=list)
