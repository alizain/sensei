"""Main application combining API and MCP servers."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp.utilities.logging import configure_logging

from sensei.kura import kura
from sensei.scout import scout
from sensei.server.api import api_app
from sensei.server.mcp import mcp
from sensei.tome.server import tome

# Configure logging (after imports, before app creation)
configure_logging(level="DEBUG")  # fastmcp logger
configure_logging(level="DEBUG", logger=logging.getLogger("sensei"))  # sensei logger

# Quiet noisy libraries (commented out until needed)
# logging.getLogger("httpx").setLevel(logging.INFO)
# logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

mcp_app = mcp.http_app(path="/mcp", stateless_http=True)
scout_mcp_app = scout.http_app(path="/scout/mcp", stateless_http=True)
kura_mcp_app = kura.http_app(path="/kura/mcp", stateless_http=True)
tome_mcp_app = tome.http_app(path="/tome/mcp", stateless_http=True)


@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    """Combined lifespan: database init + MCP session managers."""
    # Ensure database is ready first (idempotent - individual service lifespans will no-op)
    from sensei.database.local import ensure_db_ready

    await ensure_db_ready()

    async with mcp_app.lifespan(app):
        async with scout_mcp_app.lifespan(app):
            async with kura_mcp_app.lifespan(app):
                async with tome_mcp_app.lifespan(app):
                    yield


# Create combined app
app = FastAPI(
    title="Sensei",
    description="Intelligent documentation agent for AI coding assistants",
    version="0.1.0",
    routes=[
        *mcp_app.routes,  # MCP routes at /mcp/*
        *scout_mcp_app.routes,  # Scout routes at /scout/mcp/*
        *kura_mcp_app.routes,  # Kura routes at /kura/mcp/*
        *tome_mcp_app.routes,  # Tome routes at /tome/mcp/*
        *api_app.routes,  # API routes at /query, /rate, /health
    ],
    lifespan=combined_lifespan,
)
