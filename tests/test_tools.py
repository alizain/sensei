"""Tests for tools with dependency-injected HTTP client."""

import pytest

from sensei.deps import Deps
from sensei.tools.exec_plan import add_exec_plan, update_exec_plan


class DummyCtx:
    def __init__(self):
        self.deps = Deps()


@pytest.mark.asyncio
async def test_exec_plan_add_and_update():
    ctx = DummyCtx()

    add_result = await add_exec_plan(ctx)
    assert "ExecPlan template added" in add_result.data
    # Plan is now stored directly in deps
    assert ctx.deps.exec_plan is not None
    assert "Documentation Research ExecPlan" in ctx.deps.exec_plan

    updated = "# Updated plan"
    update_result = await update_exec_plan(ctx, updated)
    assert "ExecPlan updated" in update_result.data
    assert ctx.deps.exec_plan == updated


@pytest.mark.asyncio
async def test_exec_plan_update_without_plan():
    ctx = DummyCtx()
    # No exec_plan set, so update should return NoResults
    from sensei.types import NoResults

    result = await update_exec_plan(ctx, "# plan")
    assert isinstance(result, NoResults)
