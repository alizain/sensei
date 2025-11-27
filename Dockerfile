# Sensei Dockerfile

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY .python-version .
COPY README.md .
COPY sensei/ sensei/

# Install dependencies
RUN uv sync --no-dev

# Expose API port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command runs both API and MCP servers
# Can be overridden with: docker run sensei api
# or: docker run sensei mcp
CMD ["uv", "run", "sensei"]
