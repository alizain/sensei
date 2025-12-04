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

### Sensei (Core)

- `sensei_query` - Query Sensei for documentation and code examples
- `sensei_feedback` - Rate responses to improve quality

### Scout (Repository Exploration)

- `scout_glob` - Find files by pattern
- `scout_read` - Read file contents
- `scout_grep` - Search for patterns with context
- `scout_tree` - Directory structure

### Kura (Response Cache)

- `kura_search` - Search cached documentation responses
- `kura_get` - Retrieve a cached response by ID

### Tome (llms.txt Documentation)

- `tome_get` - Get documentation from an llms.txt domain
- `tome_search` - Search documentation within an llms.txt domain

## Running the Server

```bash
# Unified MCP server (stdio - for Claude Desktop, etc.)
python -m sensei

# Unified MCP server (HTTP)
python -m sensei -t http --port 8000

# REST API server (HTTP)
python -m sensei.api --port 8000
```

Or run individual MCP servers:

```bash
python -m sensei.scout   # Scout MCP server (stdio)
python -m sensei.kura    # Kura MCP server (stdio)
python -m sensei.tome    # Tome MCP server (stdio)
```
