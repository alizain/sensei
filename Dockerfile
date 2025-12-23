FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ripgrep \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install lstr from pre-built binary
RUN curl -L https://github.com/bgreenwell/lstr/releases/download/v0.2.1/lstr-linux-x86_64.tar.gz \
    | tar xz -C /usr/local/bin

# Set up app
WORKDIR /app
COPY . .
RUN uv sync --locked

# Volume mount point for Scout cache
RUN mkdir -p /data/scout

# Expose port
EXPOSE 8000

CMD ["uv", "run", "--no-sync", "start"]
