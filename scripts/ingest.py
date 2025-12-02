#!/usr/bin/env python
"""
Ingest documentation from a domain's llms.txt file.

Usage:
    uv run python scripts/ingest.py react.dev
    uv run python scripts/ingest.py react.dev --depth 1
    uv run python scripts/ingest.py react.dev -v      # INFO logging
    uv run python scripts/ingest.py react.dev -vv     # DEBUG logging (shows all links)
"""

import argparse
import asyncio
import logging
import sys

from fastmcp.utilities.logging import configure_logging

from sensei.database.local import ensure_db_ready
from sensei.tome.crawler import ingest_domain
from sensei.types import Success


async def run_ingest(domain: str, max_depth: int) -> int:
    """Run ingest_domain and return exit code."""
    await ensure_db_ready()

    print(f"Ingesting {domain} (max_depth={max_depth})...")

    result = await ingest_domain(domain, max_depth)

    match result:
        case Success(data):
            print(f"✓ Ingested {data.domain}: {data.documents_added} documents")
            if data.warnings:
                print(f"  Warnings: {len(data.warnings)}")
                for w in data.warnings[:5]:
                    print(f"    - {w}")
                if len(data.warnings) > 5:
                    print(f"    ... and {len(data.warnings) - 5} more")
            if data.failures:
                print(f"  Failures: {len(data.failures)}")
                for f in data.failures[:5]:
                    print(f"    - {f}")
                if len(data.failures) > 5:
                    print(f"    ... and {len(data.failures) - 5} more")
            return 0
        case _:
            print("✗ Ingest failed")
            return 1


def main():
    parser = argparse.ArgumentParser(description="Ingest documentation from a domain's llms.txt file")
    parser.add_argument(
        "domain",
        help="Domain to ingest (e.g., 'react.dev' or 'https://react.dev')",
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=3,
        help="Maximum link depth to follow (0=only llms.txt, default=3)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )

    args = parser.parse_args()

    # Configure logging consistently with main app (sets sensei logger explicitly,
    # immune to Crawlee overriding root logger level)
    if args.verbose >= 2:
        level = "DEBUG"
    elif args.verbose == 1:
        level = "INFO"
    else:
        level = "WARNING"

    configure_logging(level=level)
    configure_logging(level=level, logger=logging.getLogger("sensei"))

    exit_code = asyncio.run(run_ingest(args.domain, args.depth))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
