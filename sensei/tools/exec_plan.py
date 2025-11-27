"""ExecPlan tooling for Sensei."""

import logging
from datetime import datetime
from textwrap import dedent
from typing import Dict, Optional

from pydantic_ai import RunContext

from sensei.deps import Deps

logger = logging.getLogger(__name__)

# =============================================================================
# In-memory storage
# =============================================================================

_exec_plans: Dict[str, str] = {}


def get_plan(query_id: str) -> Optional[str]:
	"""Retrieve the ExecPlan for a query if it exists."""
	return _exec_plans.get(query_id)


def set_plan(query_id: str, plan: str) -> None:
	"""Store or replace the ExecPlan for a query."""
	_exec_plans[query_id] = plan


def clear_plan(query_id: str) -> None:
	"""Remove the ExecPlan for a query."""
	_exec_plans.pop(query_id, None)


# =============================================================================
# Tools
# =============================================================================

EXEC_PLAN_TEMPLATE = dedent(
	"""\
    # Documentation Research ExecPlan

    ## Purpose / Big Picture

    (Fill this in: Why this research matters and what the user will gain)

    ## Progress

    - [ ] Identify sources to check
    - [ ] Query sources
    - [ ] Synthesize findings
    - [ ] Generate final documentation

    ## Surprises & Discoveries

    (Document unexpected findings as you discover them)

    ## Decision Log

    - Decision: Created this ExecPlan
      Rationale: (Fill this in: why you decided to create a plan)
      Date: {timestamp}

    ## Research Plan

    **Sources to Check:**
    (Fill this in with specific sources)

    **Synthesis Strategy:**
    (Fill this in: Your approach to combining results)

    ## Validation

    **Success Criteria:**
    - Accurate, working code examples
    - Clear explanations
    - Multiple source verification
    """
)


async def add_exec_plan(ctx: RunContext[Deps]) -> str:
	"""Add an ExecPlan template to guide your research work."""
	if not ctx.deps or not ctx.deps.query_id:
		logger.warning("Cannot create ExecPlan: missing query_id")
		return "Error: missing query_id; cannot create ExecPlan."

	logger.info(f"Creating ExecPlan for query_id={ctx.deps.query_id}")
	plan = EXEC_PLAN_TEMPLATE.format(timestamp=datetime.now().isoformat())
	set_plan(ctx.deps.query_id, plan)
	logger.debug(f"ExecPlan created for query_id={ctx.deps.query_id}")

	return "ExecPlan template added to your instructions. Use update_exec_plan() to fill it in and track your progress."


async def update_exec_plan(ctx: RunContext[Deps], updated_plan: str) -> str:
	"""Update your ExecPlan with progress, decisions, and discoveries."""
	if not ctx.deps or not ctx.deps.query_id:
		logger.warning("Cannot update ExecPlan: missing query_id")
		return "Error: missing query_id; cannot update ExecPlan."

	current_plan = get_plan(ctx.deps.query_id)

	if not current_plan:
		logger.warning(f"Cannot update ExecPlan: no plan exists for query_id={ctx.deps.query_id}")
		return "No ExecPlan exists yet. Create one with add_exec_plan() first."

	logger.info(f"Updating ExecPlan for query_id={ctx.deps.query_id}")
	set_plan(ctx.deps.query_id, updated_plan)
	logger.debug(f"ExecPlan updated for query_id={ctx.deps.query_id}, length={len(updated_plan)}")

	return "ExecPlan updated. Continue your research."
