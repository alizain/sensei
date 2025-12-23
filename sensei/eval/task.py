"""Task functions for pydantic-evals evaluation runs."""

from sensei import deps as deps_module
from sensei.agent import create_agent


async def run_agent(query: str) -> str:
    """Run the Sensei agent for a single eval case and return the output."""
    agent = create_agent(
        include_spawn=False,
        instrument=True,
    )
    deps = deps_module.Deps()
    result = await agent.run(query, deps=deps)
    return result.output
