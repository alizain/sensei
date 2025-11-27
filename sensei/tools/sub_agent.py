"""Sub-agent factory and spawning for Sensei."""

import logging
import uuid
from typing import Optional

from pydantic_ai import Agent, RunContext, Tool

from sensei.config import settings
from sensei.database.storage import get_query, save_query, search_queries_fts
from sensei.deps import Deps
from sensei.prompts import build_prompt
from sensei.tools.cache import _compute_age_days
from sensei.types import SubSenseiResult, ToolError

logger = logging.getLogger(__name__)


# =============================================================================
# Sub-Agent Factory
# =============================================================================


def create_sub_agent(can_spawn: bool = False) -> Agent:
	"""Create a sub-agent with restricted toolset.

	Args:
	    can_spawn: Whether this sub-agent can spawn further sub-agents

	Returns:
	    A configured Agent for answering sub-questions
	"""
	from pydantic_ai.models.openai import OpenAIChatModel
	from pydantic_ai.providers.grok import GrokProvider

	from sensei.tools.context7 import create_context7_server
	from sensei.tools.scout import create_scout_server
	from sensei.tools.tavily import create_tavily_server

	tools = []
	if can_spawn:
		tools.append(Tool(spawn_sub_agent, takes_ctx=True))

	grok_model = OpenAIChatModel(
		"grok-4-1-fast-reasoning",
		provider=GrokProvider(api_key=settings.grok_api_key),
	)

	return Agent(
		model=grok_model,
		system_prompt=build_prompt("sub_agent_mcp"),
		deps_type=Deps,
		output_type=str,
		toolsets=[
			create_context7_server(settings.context7_api_key),
			create_tavily_server(settings.tavily_api_key),
			create_scout_server(),
		],
		tools=tools,
	)


# =============================================================================
# Cache Helpers
# =============================================================================


async def check_cache_for_question(question: str) -> SubSenseiResult | None:
	"""Check if a question has a cached response.

	Args:
	    question: The question to search for

	Returns:
	    SubSenseiResult if cache hit found, None otherwise
	"""
	hits = await search_queries_fts(question, limit=1)
	if not hits:
		return None

	query = await get_query(hits[0].query_id)
	if not query:
		return None

	return SubSenseiResult(
		query_id=query.query_id,
		response_markdown=query.output,
		from_cache=True,
		age_days=_compute_age_days(query.created_at),
	)


def format_sub_result(result: SubSenseiResult) -> str:
	"""Format SubSenseiResult to string for LLM consumption.

	This is the edge where we convert rich types to strings.
	"""
	if result.from_cache and result.age_days is not None:
		return f"[From cache ({result.age_days} days old)]\n\n{result.response_markdown}"
	return result.response_markdown


# =============================================================================
# Sub-Agent Spawning
# =============================================================================


async def spawn_sub_agent(
	ctx: RunContext[Deps],
	sub_question: str,
	max_depth: Optional[int] = None,
) -> str:
	"""Spawn a sub-agent to answer a focused sub-question.

	Use this to decompose complex questions into simpler sub-questions.
	Each sub-question gets answered independently and cached.

	Args:
	    ctx: Run context with depth tracking
	    sub_question: The focused sub-question to answer
	    max_depth: Override max recursion depth (optional)

	Returns:
	    The sub-agent's answer (cached automatically)
	"""
	if not ctx.deps or not ctx.deps.query_id:
		raise ToolError("Missing query_id in context")

	current_depth = ctx.deps.current_depth
	effective_max = max_depth if max_depth is not None else ctx.deps.max_depth

	if current_depth >= effective_max:
		return f"Cannot spawn sub-agent: at max depth ({current_depth}/{effective_max})"

	logger.info(f"Spawning sub-agent: depth={current_depth + 1}, question={sub_question[:50]}...")

	# Check cache first
	cached_result = await check_cache_for_question(sub_question)
	if cached_result:
		logger.info(f"Sub-question cache hit: {cached_result.query_id}")
		return format_sub_result(cached_result)

	# No cache hit - run sub-agent
	sub_query_id = f"sub-{uuid.uuid4().hex[:12]}"
	can_spawn = (current_depth + 1) < effective_max

	sub_agent = create_sub_agent(can_spawn=can_spawn)
	sub_deps = Deps(
		query_id=sub_query_id,
		parent_query_id=ctx.deps.query_id,
		current_depth=current_depth + 1,
		max_depth=effective_max,
		http_client=ctx.deps.http_client,
	)

	result = await sub_agent.run(sub_question, deps=sub_deps)

	# Cache the result
	await save_query(
		query_id=sub_query_id,
		query=sub_question,
		output=result.output,
		messages=result.new_messages_json(),
		parent_query_id=ctx.deps.query_id,
		depth=current_depth + 1,
	)

	logger.info(f"Sub-agent completed: {sub_query_id}")
	return result.output
