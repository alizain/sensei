# Contributing to Sensei

## Development Setup

```bash
uv sync --group dev
uv run pre-commit install
```

Sensei stores development data under `~/.sensei/` by default.

## Self-Hosting

Sensei requires PostgreSQL 17+ with migrations applied:

```bash
alembic upgrade head
```

Set `SENSEI_DATABASE_URL` in your runtime configuration.

## Versioning

Versions are managed via `uv version`. A pre-commit hook automatically syncs versions to README.md, plugin.json, and package.json:

```bash
uv version --bump patch   # Bumps pyproject.toml
git add pyproject.toml
git commit                # Hook syncs other files automatically
```

## Code Style

See [AGENTS.md](AGENTS.md) for coding conventions and architectural guidelines.
