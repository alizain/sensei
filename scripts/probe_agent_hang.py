"""Probe Sensei agent hangs by logging in-flight HTTP requests."""

from __future__ import annotations

import argparse
import asyncio
import time
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass
from itertools import count
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import aiohttp
import httpx

from sensei.eval.task import run_agent


@dataclass(frozen=True)
class InFlight:
    desc: str
    start: float
    stack: list[str]


_counter = count(1)
_in_flight: dict[int, InFlight] = {}
_stack_limit = 12


def _log(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def _redact_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if not parsed.query:
        return raw_url

    redacted_params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if any(token in key_lower for token in ("key", "token", "secret", "auth", "api")):
            redacted_params.append((key, "REDACTED"))
        else:
            redacted_params.append((key, value))

    return urlunparse(parsed._replace(query=urlencode(redacted_params)))


def _record(desc: str) -> int:
    request_id = next(_counter)
    stack = traceback.format_stack(limit=_stack_limit)
    _in_flight[request_id] = InFlight(desc=desc, start=time.monotonic(), stack=stack)
    _log(f"START {desc}")
    return request_id


def _finish(request_id: int, status: str) -> None:
    info = _in_flight.pop(request_id, None)
    if not info:
        return
    elapsed = time.monotonic() - info.start
    _log(f"END   {info.desc} ({status}) after {elapsed:.2f}s")


def _install_httpx_patch() -> None:
    original_send = httpx.AsyncClient.send

    async def _send(self: httpx.AsyncClient, request: httpx.Request, *args, **kwargs):
        desc = f"httpx send {request.method} {_redact_url(str(request.url))}"
        request_id = _record(desc)
        try:
            response = await original_send(self, request, *args, **kwargs)
            _finish(request_id, f"status {response.status_code}")
            return response
        except Exception as exc:  # pragma: no cover - probe only
            _finish(request_id, f"error {type(exc).__name__}")
            raise

    httpx.AsyncClient.send = _send  # type: ignore[assignment]

    original_stream = httpx.AsyncClient.stream

    @asynccontextmanager
    async def _stream(self: httpx.AsyncClient, method: str, url: str, *args, **kwargs):
        desc = f"httpx stream {method} {_redact_url(str(url))}"
        request_id = _record(desc)
        try:
            async with original_stream(self, method, url, *args, **kwargs) as response:
                _log(f"INFO  httpx stream response {method} {_redact_url(str(url))} status {response.status_code}")
                yield response
            _finish(request_id, "stream closed")
        except Exception as exc:  # pragma: no cover - probe only
            _finish(request_id, f"stream error {type(exc).__name__}")
            raise

    httpx.AsyncClient.stream = _stream  # type: ignore[assignment]


def _install_aiohttp_patch() -> None:
    original_request = aiohttp.ClientSession._request

    async def _request(self: aiohttp.ClientSession, method: str, url: str, *args, **kwargs):
        desc = f"aiohttp request {method} {_redact_url(str(url))}"
        request_id = _record(desc)
        try:
            response = await original_request(self, method, url, *args, **kwargs)
            _finish(request_id, f"status {response.status}")
            return response
        except Exception as exc:  # pragma: no cover - probe only
            _finish(request_id, f"error {type(exc).__name__}")
            raise

    aiohttp.ClientSession._request = _request  # type: ignore[assignment]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Sensei agent hangs by logging in-flight HTTP requests.")
    parser.add_argument(
        "--query",
        help="Single query to run through the agent.",
        default="How can I use langfuse and logfire together as instrumentation in pydanticAI?",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=6.0,
        help="Timeout in seconds before dumping pending requests.",
    )
    parser.add_argument(
        "--stack-limit",
        type=int,
        default=12,
        help="Limit stack frames captured for pending requests.",
    )
    return parser.parse_args()


async def _run_probe(query: str, timeout: float) -> int:
    task = asyncio.create_task(run_agent(query))
    try:
        await asyncio.wait_for(task, timeout=timeout)
        _log("run_agent completed within timeout")
        return 0
    except asyncio.TimeoutError:
        _log("run_agent timed out; pending requests:")
        if not _in_flight:
            _log("  (none recorded)")
        for info in _in_flight.values():
            elapsed = time.monotonic() - info.start
            _log(f"  - {info.desc} pending for {elapsed:.2f}s")
            _log("    stack (most recent call last):")
            for line in "".join(info.stack).rstrip().splitlines():
                _log(f"    {line}")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return 2
    except Exception:  # pragma: no cover - probe only
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise


def main() -> int:
    global _stack_limit
    args = _parse_args()
    _stack_limit = max(1, args.stack_limit)
    _install_httpx_patch()
    _install_aiohttp_patch()
    return asyncio.run(_run_probe(args.query, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())
