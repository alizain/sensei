**Note**: This project uses [bd (beads)](https://github.com/steveyegge/beads)
for issue tracking. Use `bd` commands instead of markdown TODOs.
See AGENTS.md for workflow details.

## Coding style

- **NEVER USE LAZY IMPORTS**. NEVER. Always use module-level imports. If you're facing cycles, use the system-thinking-before-implementing to figure out the correct way to solve the cycle. LAZY IMPORTS ARE ALWAYS A HACK. NEVER USE THEM. NO MATTER WHAT THE REASON.

## Environment Variables

**NEVER suggest modifying environment variables or creating .env files.** Configuration is managed through `sensei/config.py` with hardcoded defaults. The user manages their own environment—do not tell them to set, export, or modify any environment variables.

## ExecPlans

When writing complex features or significant refactors, use an ExecPlan (as described in `.agent/PLANS.md`) from design to implementation. Create ExecPlans in `docs/execplans/`

## Error Handling

Use typed exceptions from `sensei/types.py`. Keep structured errors until the edge—only convert to strings/HTTP codes at API/MCP boundaries.

| Exception | When to Use | Behavior |
|-----------|-------------|----------|
| `BrokenInvariant` | Config/setup errors (missing API key) | Halts agent, HTTP 503 |
| `TransientError` | Temporary failures (network timeout) | Returns string to LLM |
| `ToolError` | Tool failures (bad input, API error) | Returns string to LLM |

**Best practices:**
- **Preserve exception chains** with `raise ... from e` so root cause is traceable
- **Return strings for recoverable errors** so the LLM can reason and try alternatives
- **Only halt on `BrokenInvariant`**—config errors can't be worked around
- **Never return `"Error: ..."` strings**—raise typed exceptions instead

```python
async def search_foo(...) -> Success[str] | NoResults:
    if not api_key:
        raise BrokenInvariant("API key not configured")
    try:
        response = await client.get(...)
    except httpx.TimeoutException as e:
        raise TransientError("Request timed out") from e  # preserve chain

    if not results:
        return NoResults()
    return Success(format_results(...))
```

## Result Types

Tools return `Success[T] | NoResults`, never error strings. This separates "found nothing" from "something went wrong"—critical for the LLM to make good decisions.

- `Success[str]` - Tool found data
- `NoResults` - Tool ran successfully but found nothing (not an error)

**Best practices:**
- **Use pattern matching** to handle results—`match result: case Success(data): ...`
- **`NoResults` is not an error**—it means the search worked, just nothing matched
- **Wrap tools for PydanticAI** with `wrap_tool()` from `sensei/tools/common.py`
- **Keep rich types internally**—only stringify at the PydanticAI boundary

## Domain Models

Define domain models once in `sensei/types.py`. Use them across all layers—core, storage, and edges. This is the single source of truth for your domain.

**Best practices:**
- **One definition, used everywhere**—no duplicating fields across API/DB models
- **Pass models, not individual fields**—`save_rating(rating: Rating)` not `save_rating(query_id, correctness, ...)`
- **Convert at the edges only**—API/MCP layers convert wire format ↔ domain models
- **Use Pydantic for validation**—`Field(..., ge=1, le=5)` validates once, everywhere

```python
# In types.py - single source of truth
class Rating(BaseModel):
    query_id: str
    correctness: int = Field(..., ge=1, le=5)
    ...

# In core.py - pass the model
async def handle_rating(rating: Rating) -> None:
    await storage.save_rating(rating)

# In storage.py - accept the model
async def save_rating(rating: Rating) -> None:
    record = RatingModel(**rating.model_dump())
    ...

# At edges - convert from wire format
rating = Rating(**request.model_dump())
await core.handle_rating(rating)
```

## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Auto-syncs to JSONL for version control
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**
```bash
bd ready --json
```

**Create new issues:**
```bash
bd create "Issue title" -t bug|feature|task -p 0-4 --json
bd create "Issue title" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**
```bash
bd update bd-42 --status in_progress --json
bd update bd-42 --priority 1 --json
```

**Complete work:**
```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task**: `bd update <id> --status in_progress`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`
6. **Commit together**: Always commit the `.beads/issues.jsonl` file together with the code changes so issue state stays in sync with code state

### Auto-Sync

bd automatically syncs with git:
- Exports to `.beads/issues.jsonl` after changes (5s debounce)
- Imports from JSONL when newer (e.g., after `git pull`)
- No manual export/import needed!

### GitHub Copilot Integration

If using GitHub Copilot, also create `.github/copilot-instructions.md` for automatic instruction loading.
Run `bd onboard` to get the content, or see step 2 of the onboard instructions.

### MCP Server

You should have access to beads commands via MCP. Use `mcp__beads__*` functions instead of CLI commands.

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ✅ Store AI planning docs in `history/` directory
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems
- ❌ Do NOT clutter repo root with planning documents

For more details, see README.md and QUICKSTART.md.
