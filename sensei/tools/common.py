"""Shared helpers for Sensei tools."""

from typing import Any, Callable, Iterable

import httpx
from pydantic_ai import RunContext

from sensei.deps import Deps

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def format_entries(source: str, entries: Iterable[dict[str, Any]]) -> str:
	"""Format tool results into markdown."""
	formatted_sections = []

	for idx, entry in enumerate(entries, 1):
		title = entry.get("title") or entry.get("name") or f"Result {idx}"
		snippet = entry.get("snippet") or entry.get("summary") or entry.get("content") or ""
		code = entry.get("code") or ""
		link = entry.get("link") or entry.get("url") or ""

		section_parts = [f"## {idx}. {title}"]
		if snippet:
			section_parts.append(snippet.strip())
		if code:
			section_parts.append("```")
			section_parts.append(code.strip())
			section_parts.append("```")
		if link:
			section_parts.append(f"- Source: {link}")

		formatted_sections.append("\n\n".join(section_parts).strip())

	if not formatted_sections:
		return ""

	body = "\n\n".join(formatted_sections)
	return f"# {source} results\n\n{body}"


async def get_client(ctx: RunContext[Deps]) -> tuple[httpx.AsyncClient, bool]:
	"""Return an HTTP client and whether we created it."""
	if getattr(ctx, "deps", None) and getattr(ctx.deps, "http_client", None):
		return ctx.deps.http_client, False  # type: ignore[return-value]
	client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
	return client, True


def wrap_tool(fn: Callable) -> Callable:
	"""Wrap a tool function to convert rich types to strings for PydanticAI.

	PydanticAI tools must return strings. This wrapper:
	- Converts Success[T] to T (the data)
	- Converts NoResults to "No results found."
	- Converts TransientError/ToolError to error strings (so LLM can reason)
	- Re-raises BrokenInvariant (config errors halt the agent)
	"""
	from functools import wraps

	from sensei.types import (
		BrokenInvariant,
		NoResults,
		Success,
		ToolError,
		TransientError,
	)

	@wraps(fn)
	async def wrapped(*args: Any, **kwargs: Any) -> str:
		try:
			result = await fn(*args, **kwargs)
			match result:
				case Success(data):
					return data
				case NoResults():
					return "No results found."
				case _:
					return str(result)
		except TransientError as e:
			return f"Tool temporarily unavailable: {e}"
		except ToolError as e:
			return f"Tool failed: {e}"
		except BrokenInvariant:
			raise  # Config errors halt the agent

	return wrapped
