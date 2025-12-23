"""Shared dependency container for Sensei tools and agent."""

from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field

from sensei.types import CacheHit


class Deps(BaseModel):
    """Dependency container passed to tools.

    Deps carries runtime context through agent execution:
    - cache_hits: Pre-fetched cache results for root queries
    - current_depth: Recursion depth for sub-agent spawning
    - exec_plan: Request-scoped execution plan
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    http_client: httpx.AsyncClient | None = None
    # Prefetched cache hits (root queries only)
    cache_hits: list[CacheHit] = Field(default_factory=list)
    # Sub-agent recursion depth (0 = root query)
    current_depth: int = 0
    # ExecPlan for this request (request-scoped, no global state)
    exec_plan: Optional[str] = None
