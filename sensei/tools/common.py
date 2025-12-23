"""Shared helpers for Sensei tools."""

from functools import wraps
from typing import Any, Callable

import logfire
import sentry_sdk

from sensei.types import BrokenInvariant, NoResults, Success, ToolError, TransientError


def wrap_tool(fn: Callable) -> Callable:
    """Wrap a tool function to convert rich types to strings for PydanticAI.

    PydanticAI tools must return strings. This wrapper:
    - Converts Success[T] to T (the data)
    - Converts NoResults to "No results found."
    - Converts TransientError/ToolError to error strings (so LLM can reason)
    - Re-raises BrokenInvariant (config errors halt the agent)
    """

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
            sentry_sdk.capture_exception(e)
            logfire.exception(str(e), tool=fn.__name__)
            return f"Tool temporarily unavailable: {e}"
        except ToolError as e:
            sentry_sdk.capture_exception(e)
            logfire.exception(str(e), tool=fn.__name__)
            return f"Tool failed: {e}"
        except BrokenInvariant:
            raise  # Config errors halt the agent

    return wrapped
