"""PydanticAI agent definition for Sensei."""

import logging

import sentry_sdk
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from sensei import deps as deps_module
from sensei.build import build_deps
from sensei.prompts import build_prompt
from sensei.settings import general_settings, sensei_settings
from sensei.tools.common import wrap_tool
from sensei.tools.context7 import create_context7_server
from sensei.tools.exec_plan import add_exec_plan, update_exec_plan
from sensei.tools.httpx import create_httpx_server
from sensei.tools.scout import create_scout_server
from sensei.tools.tavily import create_tavily_server
from sensei.tools.tome import create_tome_server
from sensei.types import ToolError

logger = logging.getLogger(__name__)

# Configure logfire only if token is available
if general_settings.logfire_token:
    import logfire

    logfire.configure(token=general_settings.logfire_token, service_name=general_settings.logfire_service_name)
    logfire.instrument_pydantic_ai()
    Agent.instrument_all()

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
        query_truncated = hit.query[:100] + "..." if len(hit.query) > 100 else hit.query
        lines.append(f"- **{hit.id}**{lib_str} ({age_str}): {query_truncated}")
    lines.append("\nUse `kura_get(query_id)` to retrieve full answer if relevant.\n")
    return "\n".join(lines)


# =============================================================================
# Helpers
# =============================================================================


def get_model_settings(model: str):
    """Return provider-appropriate ModelSettings with thinking enabled."""
    provider = model.split(":")[0] if ":" in model else model.split("/")[0]

    match provider:
        case "google-gla" | "google-vertex":
            return GoogleModelSettings(google_thinking_config={"thinking_level": "high", "include_thoughts": True})
        case "anthropic":
            return AnthropicModelSettings(
                anthropic_thinking={"type": "enabled", "budget_tokens": 15000},
                max_tokens=25000,
                anthropic_cache_instructions=True,
            )
        case "openai":
            return OpenAIResponsesModelSettings(
                openai_reasoning_effort="medium",
                openai_reasoning_summary="detailed",
            )
        case _:
            return None  # No special settings, use defaults


def event_stream_handler(*args, **kwargs):
    print(args)
    print(kwargs)


# =============================================================================
# Agent Factory
# =============================================================================


async def spawn_sub_agent(
    ctx: RunContext[deps_module.Deps],
    sub_question: str,
) -> str:
    """Spawn a sub-agent to answer a focused sub-question.

    Use this to decompose complex questions into simpler sub-questions.
    Sub-agents always generate fresh content (no cache lookup).

    Args:
        ctx: Run context with parent deps
        sub_question: The focused sub-question to answer

    Returns:
        The sub-agent's answer, or error message if depth limit exceeded
    """
    logger.info(f"Spawning sub-agent: question={sub_question[:50]}...")

    try:
        sub_deps = await build_deps(sub_question, ctx)
    except ToolError as e:
        sentry_sdk.capture_exception(e)
        return str(e)  # Return error message for agent to see

    sub_agent = create_sub_agent()
    result = await sub_agent.run(sub_question, deps=sub_deps)
    logger.info("Sub-agent completed")
    return result.output


def create_agent(
    include_spawn: bool = True,
    include_exec_plan: bool = True,
    instrument: bool | object = True,
    model: object | None = None,
    system_prompt: str | None = None,
) -> Agent[deps_module.Deps, str]:
    """Create an agent with configurable tools.

    Args:
        include_spawn: Include spawn_sub_agent tool (False for sub-agents)
        include_exec_plan: Include exec plan tools (False for sub-agents)
        instrument: Instrumentation config (True for default tracing, or custom settings)
        model: Model to use (defaults to DEFAULT_MODEL)
        system_prompt: Override the default system prompt (for optimization/testing)

    Returns:
        Configured Agent instance
    """
    tools = []
    if include_exec_plan:
        tools.append(Tool(wrap_tool(add_exec_plan), takes_ctx=True))
        tools.append(Tool(wrap_tool(update_exec_plan), takes_ctx=True))
    if include_spawn:
        tools.append(Tool(spawn_sub_agent, takes_ctx=True))

    resolved_model = model or sensei_settings.model
    return Agent(
        model=resolved_model,
        system_prompt=system_prompt or SYSTEM_PROMPT,
        deps_type=deps_module.Deps,
        output_type=str,
        model_settings=get_model_settings(resolved_model),
        toolsets=[
            create_context7_server(general_settings.context7_api_key),
            # create_grep_server(),
            create_tavily_server(general_settings.tavily_api_key),
            create_scout_server(),
            # create_kura_server(),
            create_tome_server(),
            create_httpx_server(),
        ],
        tools=tools,
        # event_stream_handler=event_stream_handler,
        instructions=[current_exec_plan, prefetch_cache_hits],
        instrument=instrument,
    )


def create_sub_agent() -> Agent[deps_module.Deps, str]:
    """Create a sub-agent with restricted tools.

    Sub-agents don't have spawn or exec_plan tools to prevent
    infinite recursion and keep them focused on answering sub-questions.

    Returns:
        Configured Agent instance for sub-questions
    """
    return create_agent(include_spawn=False, include_exec_plan=True)
