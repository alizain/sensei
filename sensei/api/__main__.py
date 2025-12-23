import argparse

import uvicorn

from sensei.api import app
from sensei.settings import general_settings


def main():
    """Start the Sensei API server."""
    parser = argparse.ArgumentParser(prog="sensei.api", description="Sensei REST API server")
    parser.add_argument(
        "--host",
        default=general_settings.host,
        help=f"Host to bind to (default: {general_settings.host})",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=general_settings.port,
        help=f"Port to bind to (default: {general_settings.port})",
    )

    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, ws="websockets-sansio")


if __name__ == "__main__":
    main()
