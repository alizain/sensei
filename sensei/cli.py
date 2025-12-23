"""Shared CLI utilities for MCP servers.

Usage in server.py:
    from sensei.cli import run_server

    my_server = FastMCP(name="my_server")

    def main():
        run_server(my_server, "my_server", "Description of server")

Then in __main__.py (just for `python -m` support):
    from .server import main

    if __name__ == "__main__":
        main()
"""

import argparse

from fastmcp import FastMCP


def run_server(server: FastMCP, name: str, description: str) -> None:
    """Run a FastMCP server with CLI argument parsing.

    Supports --transport (stdio/http/sse), --host, and --port options.

    Args:
        server: The FastMCP server instance to run
        name: CLI program name (e.g., "tome")
        description: CLI help description
    """
    parser = argparse.ArgumentParser(prog=name, description=description)
    parser.add_argument(
        "-t",
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to for http/sse transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8000,
        help="Port to bind to for http/sse transport (default: 8000)",
    )

    args = parser.parse_args()

    transport_kwargs = {}
    if args.transport in ("http", "sse"):
        transport_kwargs["host"] = args.host
        transport_kwargs["port"] = args.port

    server.run(transport=args.transport, **transport_kwargs)
