"""Tests for tools with dependency-injected HTTP client."""

from unittest.mock import AsyncMock

import pytest

from sensei.deps import Deps
from sensei.tools.exec_plan import add_exec_plan, update_exec_plan


class DummyCtx:
	def __init__(self, client):
		self.deps = Deps(http_client=client)


@pytest.mark.asyncio
async def test_exec_plan_add_and_update():
	ctx = DummyCtx(AsyncMock())
	ctx.deps.query_id = "q-123"

	add_result = await add_exec_plan(ctx)
	assert "ExecPlan template added" in add_result

	updated = "# plan"
	update_result = await update_exec_plan(ctx, updated)
	assert "ExecPlan updated" in update_result


@pytest.mark.asyncio
async def test_exec_plan_update_without_plan():
	ctx = DummyCtx(AsyncMock())
	ctx.deps.query_id = "q-456"
	result = await update_exec_plan(ctx, "# plan")
	assert "No ExecPlan exists" in result
