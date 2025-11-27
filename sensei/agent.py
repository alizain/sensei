"""PydanticAI agent definition for Sensei."""

import logging

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.grok import GrokProvider

from sensei import deps as deps_module
from sensei.config import settings
from sensei.prompts import build_prompt
from sensei.tools.cache import get_cached_response, search_cache
from sensei.tools.context7 import create_context7_server
from sensei.tools.exec_plan import add_exec_plan, get_plan, update_exec_plan
from sensei.tools.scout import create_scout_server
from sensei.tools.sub_agent import spawn_sub_agent
from sensei.tools.tavily import create_tavily_server
from sensei.types import BrokenInvariant

logger = logging.getLogger(__name__)

# Build system prompt from composable components
SYSTEM_PROMPT = build_prompt("full_mcp")


async def current_exec_plan(ctx: RunContext[deps_module.Deps]) -> str:
	"""Inject current ExecPlan into agent instructions if present."""
	if not ctx.deps or not ctx.deps.query_id:
		raise BrokenInvariant("No `query_id`")

	plan = get_plan(ctx.deps.query_id)
	if plan:
		return f"\n\n## YOUR CURRENT EXECPLAN\n\n{plan}\n\n"
	return ""


async def prefetch_cache_hits(ctx: RunContext[deps_module.Deps]) -> str:
	"""Inject pre-fetched cache hits into agent instructions."""
	if not ctx.deps or not ctx.deps.cache_hits:
		return ""

	lines = ["\n\n## Potentially Relevant Cache Hits\n"]
	for hit in ctx.deps.cache_hits:
		age_str = f"{hit.age_days}d ago" if hit.age_days > 0 else "today"
		lib_str = f" [{hit.library}]" if hit.library else ""
		lines.append(f"- **{hit.query_id}**{lib_str} ({age_str}): {hit.query_truncated}")
	lines.append("\nUse `get_cached_response(query_id)` to retrieve full answer if relevant.\n")
	return "\n".join(lines)


grok_model = OpenAIChatModel(
	"grok-4-1-fast-reasoning",
	provider=GrokProvider(api_key=settings.grok_api_key),
)

haiku_model = AnthropicModel("claude-sonnet-4-5", provider=AnthropicProvider(api_key=settings.anthropic_api_key))

gemini_model = GoogleModel("gemini-2.5-flash-lite", provider=GoogleProvider(api_key=settings.google_api_key))

agent = Agent(
	model=gemini_model,
	system_prompt=SYSTEM_PROMPT,
	deps_type=deps_module.Deps,
	output_type=str,
	toolsets=[
		create_context7_server(settings.context7_api_key),
		create_tavily_server(settings.tavily_api_key),
		create_scout_server(),  # Local Scout MCP server
	],
	tools=[
		Tool(add_exec_plan, takes_ctx=True),
		Tool(update_exec_plan, takes_ctx=True),
		Tool(search_cache),
		Tool(get_cached_response),
		Tool(spawn_sub_agent, takes_ctx=True),
	],
	instructions=[current_exec_plan, prefetch_cache_hits],
)
