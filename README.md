# Sensei

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.4.2-green.svg)](https://github.com/803/sensei)

**Intelligent documentation agent for AI coding assistants**

Sensei is a hyper-focused model specialized in providing correct, accurate, actionable, thorough, cross-validated guidance with working examples. Sensei handles all the synthesis, so you stay focused on your task with minimal context pollution.

AI assistants often hallucinate documentation or rely on outdated training data. Sensei fixes that by searching multiple authoritative sources and synthesizing accurate, up-to-date answers with source attribution.

## Install

```
claude plugins:install @803/sensei
```

That's it. No API keys, no configuration.

## How It Works

Sensei searches multiple sources and synthesizes the best answer:

- **Context7** - Pre-indexed official library documentation
- **Scout** - GitHub repository exploration (code search, file structure, repo maps)
- **Tavily** - AI-focused web search for docs, blogs, and discussions
- **Kura** - Cached previous answers for instant responses

Every response includes source attribution and confidence levels. Rate responses with the feedback tool to improve future results.

## Usage

Just ask your AI assistant to use Sensei when you need documentation:

> "Use Sensei to find how to set up authentication in FastAPI with OAuth2"

Sensei works best for library documentation, API references, framework guides, and "how do I do X with Y" questions.

## Prerequisites

### PostgreSQL 17+

Sensei requires PostgreSQL to be installed on your system. Install it using your package manager:

**macOS:**
```bash
brew install postgresql@17
```

**Ubuntu/Debian:**
```bash
sudo apt install postgresql-17
```

**Windows:**
Download from https://www.postgresql.org/download/windows/

**Note:** You don't need to configure PostgreSQL or create databases manually. Sensei automatically manages a local PostgreSQL instance in `~/.sensei/pgdata/` using a Unix socket (no port conflicts with system PostgreSQL).

## Development Setup

```bash
uv sync --group dev
uv run pre-commit install
```

Set `SENSEI_HOME=.sensei` in your `.env` file to keep development data local to the repo instead of `~/.sensei/`.

### Versioning

Versions are managed via `uv version`. A pre-commit hook automatically syncs versions to README.md, plugin.json, and package.json:

```bash
uv version --bump patch   # Bumps pyproject.toml
git add pyproject.toml
git commit                # Hook syncs other files automatically
```

## License

MIT

---

Built with [PydanticAI](https://github.com/pydantic/pydantic-ai) and [FastMCP](https://github.com/jlowin/fastmcp)
