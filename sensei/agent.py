"""PydanticAI agent definition for Sensei."""

import logging
from datetime import datetime, timezone

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.grok import GrokProvider

from sensei import deps as deps_module
from sensei.config import settings
from sensei.database import storage
from sensei.prompts import build_prompt
from sensei.tools.common import wrap_tool
from sensei.tools.context7 import create_context7_server
from sensei.tools.exec_plan import add_exec_plan, update_exec_plan
from sensei.tools.kura import create_kura_server
from sensei.tools.scout import create_scout_server
from sensei.tools.tavily import create_tavily_server
from sensei.tools.tome import create_tome_server
from sensei.types import ToolError

logger = logging.getLogger(__name__)

# Build system prompt from composable components
SYSTEM_PROMPT = build_prompt("full_mcp")


async def current_exec_plan(ctx: RunContext[deps_module.Deps]) -> str:
    """Inject current ExecPlan into agent instructions if present."""
    if ctx.deps and ctx.deps.exec_plan:
        return f"\n\n## YOUR CURRENT EXECPLAN\n\n{ctx.deps.exec_plan}\n\n"
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
    lines.append("\nUse `kura_get(query_id)` to retrieve full answer if relevant.\n")
    return "\n".join(lines)


# =============================================================================
# Model Definitions
# =============================================================================

grok_model = OpenAIChatModel(
    "grok-4-1-fast-reasoning",
    provider=GrokProvider(api_key=settings.grok_api_key),
)

haiku_model = AnthropicModel("claude-sonnet-4-5", provider=AnthropicProvider(api_key=settings.anthropic_api_key))

gemini_model = GoogleModel("gemini-2.5-flash-lite", provider=GoogleProvider(api_key=settings.google_api_key))

# Default model for all agents
DEFAULT_MODEL = gemini_model


# =============================================================================
# Sub-Agent Helpers
# =============================================================================


def _compute_age_days(inserted_at) -> int:
    """Compute age in days from inserted_at timestamp."""
    if inserted_at is None:
        return 0
    now = datetime.now(timezone.utc)
    delta = now - inserted_at
    return delta.days


def _format_cached_result(output: str, age_days: int) -> str:
    """Format cached result with age indicator."""
    return f"[From cache ({age_days} days old)]\n\n{output}"


# =============================================================================
# Agent Factory
# =============================================================================


async def spawn_sub_agent(
    ctx: RunContext[deps_module.Deps],
    sub_question: str,
    max_depth: int | None = None,
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
    hits = await storage.search_queries(sub_question, limit=1)
    if hits:
        query = await storage.get_query(hits[0].query_id)
        if query:
            logger.info(f"Sub-question cache hit: {query.id}")
            age_days = _compute_age_days(query.inserted_at)
            return _format_cached_result(query.output, age_days)

    # No cache hit - run sub-agent
    sub_agent = create_sub_agent()
    sub_deps = deps_module.Deps(
        query_id=ctx.deps.query_id,
        parent_id=ctx.deps.query_id,
        current_depth=current_depth + 1,
        max_depth=effective_max,
    )

    result = await sub_agent.run(sub_question, deps=sub_deps)

    # Cache the result
    await storage.save_query(
        query=sub_question,
        output=result.output,
        messages=result.new_messages_json(),
        parent_id=ctx.deps.query_id,
    )

    logger.info("Sub-agent completed")
    return result.output


def create_agent(
    include_spawn: bool = True,
    include_exec_plan: bool = True,
) -> Agent[deps_module.Deps, str]:
    """Create an agent with configurable tools.

    Args:
        include_spawn: Include spawn_sub_agent tool (False for sub-agents)
        include_exec_plan: Include exec plan tools (False for sub-agents)

    Returns:
        Configured Agent instance
    """
    tools = []
    if include_exec_plan:
        tools.append(Tool(wrap_tool(add_exec_plan), takes_ctx=True))
        tools.append(Tool(wrap_tool(update_exec_plan), takes_ctx=True))
    if include_spawn:
        tools.append(Tool(spawn_sub_agent, takes_ctx=True))

    return Agent(
        model=DEFAULT_MODEL,
        system_prompt=SYSTEM_PROMPT,
        deps_type=deps_module.Deps,
        output_type=str,
        toolsets=[
            create_context7_server(settings.context7_api_key),
            create_tavily_server(settings.tavily_api_key),
            create_scout_server(),
            create_kura_server(),
            create_tome_server(),
        ],
        tools=tools,
        instructions=[current_exec_plan, prefetch_cache_hits],
    )


def create_sub_agent() -> Agent[deps_module.Deps, str]:
    """Create a sub-agent with restricted tools.

    Sub-agents don't have spawn or exec_plan tools to prevent
    infinite recursion and keep them focused on answering sub-questions.

    Returns:
        Configured Agent instance for sub-questions
    """
    return create_agent(include_spawn=False, include_exec_plan=True)


# Main agent singleton (with all tools)
agent = create_agent()
