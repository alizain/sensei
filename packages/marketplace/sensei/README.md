# Sensei Plugin for Claude Code

Documentation research agent with Scout (repository exploration) and Kura (response cache).

## Setup

1. Install the plugin in Claude Code
2. Ensure the Sensei server is running at `http://localhost:8000` (or set `SENSEI_HOST`)
3. Copy the instructions below into your project's `CLAUDE.md`

## CLAUDE.md Instructions

Add this to your project's `CLAUDE.md` to tell Claude when and how to use Sensei:

```markdown
## Documentation Research

For ANY documentation research, library questions, or external codebase exploration, spawn the **sensei** agent using the Task tool:

- "How do I use X in library Y?" → spawn sensei
- "What's the best practice for Z?" → spawn sensei
- "How does this external repo implement X?" → spawn sensei
- "Find documentation about X" → spawn sensei

Sensei has access to:
- **Scout tools** for exploring external GitHub repositories (repo_map, glob, read, grep, tree)
- **Kura tools** for searching cached documentation responses (search, get)
- Web search and official documentation sources

Do NOT attempt documentation research yourself. Always delegate to sensei for accurate, sourced answers with confidence levels.
```

## Available Tools

### Scout (Repository Exploration)

- `scout_repo_map` - Structural overview of a repo (classes, functions, signatures)
- `scout_glob` - Find files by pattern
- `scout_read` - Read file contents
- `scout_grep` - Search for patterns with context
- `scout_tree` - Directory structure

### Kura (Response Cache)

- `kura_search` - Search cached documentation responses
- `kura_get` - Retrieve a cached response by ID

## Running the Server

```bash
# Install sensei
uvx --from sensei scout  # or pip install sensei

# Run the server
uvicorn sensei:app --host 0.0.0.0 --port 8000
```

Or run individual MCP servers in stdio mode:

```bash
uvx --from sensei scout  # Scout MCP server
uvx --from sensei kura   # Kura MCP server
```
