#!/usr/bin/env python
"""
Dump the full request that Sensei would send to the model provider.

Uses PydanticAI's FunctionModel to capture the exact messages, tools,
and instructions that would be sent to the model.

Usage:
    uv run python scripts/dump_full_request.py
    uv run python scripts/dump_full_request.py --json
    uv run python scripts/dump_full_request.py --tools-only
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from uuid import uuid4

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition

from sensei import deps as deps_module
from sensei.agent import create_agent


# =============================================================================
# Core Data Structure
# =============================================================================


@dataclass
class CapturedRequest:
    """The complete request that would be sent to a model."""

    system_prompts: list[str]
    instructions: str | None
    user_prompt: str | None
    function_tools: list[ToolDefinition]
    output_tools: list[ToolDefinition]
    allow_text_output: bool


# =============================================================================
# Capture (Edge → Core)
# =============================================================================


async def capture_agent_request() -> CapturedRequest:
    """Run the agent with FunctionModel to capture what would be sent."""
    captured: dict = {}

    def capture_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured["messages"] = messages
        captured["info"] = info
        return ModelResponse(parts=[TextPart(content="[captured]")])

    agent = create_agent()

    # Create test deps to show dynamic instructions
    test_deps = deps_module.Deps(
        query_id=str(uuid4()),
        exec_plan="1. Search for React hooks documentation\n2. Find examples\n3. Summarize",
        cache_hits=[
            deps_module.CacheHit(
                query_id=uuid4(),
                query_truncated="How do React hooks work?",
                library="react",
                age_days=3,
            )
        ],
    )

    await agent.run(
        "Test query: How do I use React hooks?",
        model=FunctionModel(capture_fn),
        deps=test_deps,
    )

    return extract_request(captured["messages"], captured["info"])


# =============================================================================
# Extract (Core)
# =============================================================================


def extract_request(messages: list[ModelMessage], info: AgentInfo) -> CapturedRequest:
    """Extract structured data from raw messages and agent info."""
    system_prompts = []
    instructions = None
    user_prompt = None

    for msg in messages:
        if isinstance(msg, ModelRequest):
            if msg.instructions:
                instructions = msg.instructions
            for part in msg.parts:
                if isinstance(part, SystemPromptPart):
                    system_prompts.append(part.content)
                elif isinstance(part, UserPromptPart):
                    user_prompt = part.content

    return CapturedRequest(
        system_prompts=system_prompts,
        instructions=instructions,
        user_prompt=user_prompt,
        function_tools=list(info.function_tools),
        output_tools=list(info.output_tools),
        allow_text_output=info.allow_text_output,
    )


# =============================================================================
# Format (Core → Edge)
# =============================================================================


def format_json(req: CapturedRequest) -> str:
    """Format as JSON."""
    return json.dumps(
        {
            "system_prompts": req.system_prompts,
            "instructions": req.instructions,
            "user_prompt": req.user_prompt,
            "function_tools": [_tool_to_dict(t) for t in req.function_tools],
            "output_tools": [_tool_to_dict(t) for t in req.output_tools],
            "allow_text_output": req.allow_text_output,
        },
        indent=2,
        default=str,
    )


def format_tools_only(req: CapturedRequest) -> str:
    """Format showing only tool definitions."""
    lines = [_separator(f"FUNCTION TOOLS ({len(req.function_tools)})")]
    for tool in req.function_tools:
        lines.append(f"\n## {tool.name}")
        lines.append(f"Kind: {tool.kind}")
        if tool.description:
            lines.append(f"\n{tool.description}")
        if tool.parameters_json_schema.get("properties"):
            lines.append(f"\nParameters: {json.dumps(tool.parameters_json_schema, indent=2)}")
    return "\n".join(lines)


def format_human_readable(req: CapturedRequest) -> str:
    """Format for human reading."""
    lines = []

    # System prompts
    for i, prompt in enumerate(req.system_prompts):
        title = "SYSTEM PROMPT (main)" if i == 0 else f"SYSTEM PROMPT (part {i})"
        lines.append(_separator(title))
        lines.append(prompt)

    # Instructions
    if req.instructions:
        lines.append(_separator("INSTRUCTIONS (dynamic)"))
        lines.append(req.instructions)

    # Function tools
    lines.append(_separator(f"FUNCTION TOOLS ({len(req.function_tools)})"))
    if req.function_tools:
        for tool in req.function_tools:
            lines.append(f"\n  {tool.name}")
            desc = (tool.description or "(none)")[:100]
            if len(tool.description or "") > 100:
                desc += "..."
            lines.append(f"    Description: {desc}")
            lines.append(f"    Kind: {tool.kind}")
            if props := tool.parameters_json_schema.get("properties"):
                params = list(props.keys())[:5]
                suffix = "..." if len(props) > 5 else ""
                lines.append(f"    Parameters: {', '.join(params)}{suffix}")
    else:
        lines.append("  (No function tools)")

    # Output tools
    lines.append(_separator(f"OUTPUT TOOLS ({len(req.output_tools)})"))
    if req.output_tools:
        for tool in req.output_tools:
            lines.append(f"\n  {tool.name}")
            desc = (tool.description or "(none)")[:100] + "..."
            lines.append(f"    Description: {desc}")
    else:
        lines.append("  (No output tools)")

    # User prompt
    lines.append(_separator("USER PROMPT"))
    lines.append(req.user_prompt or "(No user prompt)")

    # Summary
    lines.append(_separator("SUMMARY"))
    sys_chars = sum(len(p) for p in req.system_prompts)
    inst_chars = len(req.instructions) if req.instructions else 0
    lines.append(f"  System prompt parts: {len(req.system_prompts)} ({sys_chars} chars)")
    lines.append(f"  Instructions: {'Yes' if req.instructions else 'No'} ({inst_chars} chars)")
    lines.append(f"  Total prompt length: {sys_chars + inst_chars} chars")
    lines.append(f"  Function tools: {len(req.function_tools)}")
    lines.append(f"  Output tools: {len(req.output_tools)}")
    lines.append(f"  Allow text output: {req.allow_text_output}")

    return "\n".join(lines)


# =============================================================================
# Helpers
# =============================================================================


def _separator(title: str) -> str:
    return f"\n{'=' * 80}\n {title}\n{'=' * 80}"


def _tool_to_dict(tool: ToolDefinition) -> dict:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters_json_schema,
        "strict": tool.strict,
        "kind": tool.kind,
    }


# =============================================================================
# CLI
# =============================================================================


async def main_async(as_json: bool, tools_only: bool) -> None:
    req = await capture_agent_request()

    if as_json:
        print(format_json(req))
    elif tools_only:
        print(format_tools_only(req))
    else:
        print(format_human_readable(req))


def main():
    parser = argparse.ArgumentParser(description="Dump Sensei's full request to the model")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--tools-only", action="store_true", help="Only show tool definitions")
    args = parser.parse_args()

    asyncio.run(main_async(as_json=args.json, tools_only=args.tools_only))


if __name__ == "__main__":
    main()
