"""Main application combining API and MCP servers."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastmcp.utilities.logging import configure_logging

from sensei.database import storage
from sensei.server.api import api_app
from sensei.server.mcp import mcp
from sensei.scout import scout

# Configure logging (after imports, before app creation)
configure_logging(level="DEBUG")  # fastmcp logger
configure_logging(level="DEBUG", logger=logging.getLogger("sensei"))  # sensei logger

# Quiet noisy libraries (commented out until needed)
# logging.getLogger("httpx").setLevel(logging.INFO)
# logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

mcp_app = mcp.http_app(path="/mcp")
scout_mcp_app = scout.http_app(path="/scout/mcp")


@asynccontextmanager
async def combined_lifespan(app: FastAPI):
	"""Combined lifespan: DB + MCP session managers."""
	# Initialize database
	await storage.init_db()

	# Start MCP session managers
	async with mcp_app.lifespan(app):
		async with scout_mcp_app.lifespan(app):
			yield
	# All shut down automatically in reverse order


# Create combined app
app = FastAPI(
	title="Sensei",
	description="Intelligent documentation agent for AI coding assistants",
	version="0.1.0",
	routes=[
		*mcp_app.routes,  # MCP routes at /mcp/*
		*scout_mcp_app.routes,  # Scout routes at /scout/mcp/*
		*api_app.routes,  # API routes at /query, /rate, /health
	],
	lifespan=combined_lifespan,
)
