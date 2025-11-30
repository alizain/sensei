"""ExecPlan tooling for Sensei."""

import logging
from datetime import datetime
from textwrap import dedent

from pydantic_ai import RunContext

from sensei.deps import Deps
from sensei.types import NoResults, Success, ToolError

logger = logging.getLogger(__name__)


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


async def add_exec_plan(ctx: RunContext[Deps]) -> Success[str]:
	"""Add an ExecPlan template to guide your research work."""
	if not ctx.deps:
		logger.warning("Cannot create ExecPlan: missing deps")
		raise ToolError("Missing deps; cannot create ExecPlan.")

	logger.info("Creating ExecPlan")
	plan = EXEC_PLAN_TEMPLATE.format(timestamp=datetime.now().isoformat())
	ctx.deps.exec_plan = plan
	logger.debug("ExecPlan created")

	return Success(
		"ExecPlan template added to your instructions. Use update_exec_plan() to fill it in and track your progress."
	)


async def update_exec_plan(ctx: RunContext[Deps], updated_plan: str) -> Success[str] | NoResults:
	"""Update your ExecPlan with progress, decisions, and discoveries."""
	if not ctx.deps:
		logger.warning("Cannot update ExecPlan: missing deps")
		raise ToolError("Missing deps; cannot update ExecPlan.")

	if not ctx.deps.exec_plan:
		logger.warning("Cannot update ExecPlan: no plan exists")
		return NoResults()

	logger.info("Updating ExecPlan")
	ctx.deps.exec_plan = updated_plan
	logger.debug(f"ExecPlan updated, length={len(updated_plan)}")

	return Success("ExecPlan updated. Continue your research.")
