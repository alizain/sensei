# Sensei OpenCode Plugin Design

**Date:** 2025-12-17
**Status:** Draft
**Related bead:** sensei-ellw (research)

## Overview

Create an OpenCode plugin that provides Sensei documentation research capabilities with an OpenCode-native experience.

## Goals

- Expose Sensei research to OpenCode users via custom tools
- Enable automated feedback collection (agent rates responses)
- Simple installation via one-liner script
- No local Python/MCP dependencies — connect to remote Sensei API

## Non-Goals

- Parity with Claude Code plugin (different approach)
- Proactive research triggers (may add later)
- User-facing feedback UI (agent handles feedback)

## Architecture

### Package Structure

```
packages/sensei-opencode/
├── package.json               # npm package config
├── tsconfig.json              # TypeScript config
├── src/
│   ├── plugin/
│   │   └── sensei.ts          # Event hooks (session.idle)
│   └── tool/
│       ├── sensei_query.ts    # Main research tool
│       └── sensei_feedback.ts # Rate response quality
├── dist/                      # Built output (published to npm)
└── README.md
```

### Distribution

- **npm package:** `@sensei-ai/opencode`
- **CDN:** unpkg serves files from npm (`https://unpkg.com/@sensei-ai/opencode@latest/dist/...`)
- **Install script:** Downloads `.ts` files from unpkg to `~/.config/opencode/`
- **Hosted installer:** Sensei REST API serves the script at `GET /opencode`

OpenCode/Bun runs TypeScript natively — no compilation needed at runtime.

## Components

### Tool: `sensei_query`

Main research entry point. Calls Sensei REST API.

**Arguments:**
| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `query` | string | Yes | The research question |
| `language` | string | No | Programming language (e.g., 'python') |
| `library` | string | No | Library/framework (e.g., 'fastapi') |
| `version` | string | No | Version spec (e.g., '>=3.0') |

**Behavior:**
1. POST to `${SENSEI_URL}/query`
2. Return markdown output + query_id footer
3. Query ID enables feedback tracking

**Example response:**
```markdown
# React Server Components

Here's how RSC works...

---
_Query ID: a1b2c3d4 (use sensei_feedback to rate this response)_
<!-- sensei:query_id=a1b2c3d4 -->
```

### Tool: `sensei_feedback`

Agent rates how helpful a Sensei response was.

**Arguments:**
| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `query_id` | string | Yes | From sensei_query response |
| `correctness` | number (1-5) | Yes | Was info accurate? |
| `relevance` | number (1-5) | Yes | Did it answer the question? |
| `usefulness` | number (1-5) | Yes | Could it be used directly? |
| `reasoning` | string | No | What worked or didn't |

**Behavior:**
1. POST to `${SENSEI_URL}/rate`
2. Includes `agent_system: "OpenCode"` for tracking
3. Returns confirmation message

### Plugin: `sensei.ts`

Event hooks for automated feedback collection.

**Hooks:**
| Event | Behavior |
|-------|----------|
| `tool.execute.after` | Capture query_id when sensei_query runs |
| `session.idle` | Prompt agent to rate the research |

**Flow:**
1. Agent calls `sensei_query` → plugin captures `query_id`
2. Session goes idle (agent finishes task)
3. Plugin injects prompt for agent to evaluate and call `sensei_feedback`
4. Agent reflects and submits rating

## Installation

### One-liner

```bash
curl -fsSL https://sensei.ai/opencode | sh
```

### What the script does

1. Creates `~/.config/opencode/plugin/` and `~/.config/opencode/tool/`
2. Downloads `.ts` files from unpkg
3. Creates `~/.config/opencode/sensei.json` config file (if missing)

### Configuration File

Tools read settings from (first match wins):

1. `<worktree>/.opencode/sensei.json` (per-project)
2. `~/.config/opencode/sensei.json` (global)

Example:

```json
{
  "url": "https://sensei.ai",
  "api_key": ""
}
```

## Authentication

Uses optional API key authentication (not OAuth):

- User obtains API key from Sensei
- Key passed via `Authorization: Bearer {key}` header
- Key stored in `sensei.json` (or omitted entirely if not required)

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | Submit research query |
| `/rate` | POST | Submit feedback rating |
| `/health` | GET | Health check (optional) |

## Open Questions

Tracked as beads for follow-up:

1. **noReply parameter:** Use `noReply: false` (runs the model) to trigger the rating; `noReply: true` is for context-only insertion.
2. **Query ID extraction:** Use a stable HTML comment marker (`<!-- sensei:query_id=... -->`) appended to tool output.
3. **Install script UX:** Framework for beautiful, portable shell scripts?

## Future Enhancements

- Proactive research triggers (on errors, unknown imports)
- Streaming support via `/query/stream`
- Version pinning in install script
- Windows PowerShell installer
