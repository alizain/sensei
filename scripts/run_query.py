#!/usr/bin/env python3
"""Run the Sensei agent with an ad-hoc query.

Usage:
    uv run scripts/run_query.py "How do I use React hooks?"
"""

import argparse
import asyncio
import sys

from pydantic_ai import messages, run

from sensei.agent import create_agent
from sensei.deps import Deps


def format_tool_call(event: messages.FunctionToolCallEvent) -> str:
    """Format a tool call for terminal display."""
    name = event.part.tool_name
    args = event.part.args_as_json_str()
    # Truncate long args
    if len(args) > 100:
        args = args[:100] + "..."
    return f"🔧 {name}({args})"


def format_tool_result(event: messages.FunctionToolResultEvent) -> str:
    """Format a tool result for terminal display."""
    content = str(event.result.content)
    # Truncate long results
    if len(content) > 200:
        content = content[:200] + "..."
    return f"   ↳ {content}"


async def run_query(query: str) -> None:
    """Run the agent with streaming output."""
    deps = Deps()

    print(f"Query: {query}\n")
    print("─" * 60)

    agent = create_agent()
    async for event in agent.run_stream_events(query, deps=deps):
        if isinstance(event, messages.FunctionToolCallEvent):
            print(format_tool_call(event))

        elif isinstance(event, messages.FunctionToolResultEvent):
            print(format_tool_result(event))

        elif isinstance(event, run.AgentRunResultEvent):
            print("\n" + "─" * 60)
            print("\nResponse:\n")
            print(event.result.output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Sensei agent with an ad-hoc query")
    parser.add_argument("query", help="The query to run")
    args = parser.parse_args()

    try:
        asyncio.run(run_query(args.query))
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
