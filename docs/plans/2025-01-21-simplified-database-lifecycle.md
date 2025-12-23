# Simplified Database Lifecycle Design

**Date:** 2025-01-21
**Status:** Approved

## Problem

The current database lifecycle management is confusing:

1. Two modes: sensei-managed PostgreSQL vs external database
2. Triple-nested lifespans (FastAPI → MCP HTTP app → Unified MCP)
3. Sub-server lifespans that only exist for `ensure_db_ready()` calls
4. Idempotency flag (`_db_ready`) to prevent duplicate initialization
5. PostgreSQL `stop()` defined but never called
6. Auto-migration on startup

## Decision

Remove sensei-managed PostgreSQL entirely. Make all database operations explicit.

## New Model

| Responsibility | Before | After |
|----------------|--------|-------|
| Start PostgreSQL | `ensure_db_ready()` | User (brew, docker, etc.) |
| Run migrations | Auto on startup | User runs `alembic upgrade head` |
| SENSEI_DATABASE_URL | Optional (has default) | Required (no default) |
| Connection validation | On startup | First query fails if unavailable |
| Disposal | Lifespan cleanup | Lifespan cleanup (unchanged) |

## Architecture

### Lifespan Hierarchy

```
FastAPI lifespan (api/__init__.py)
  └── mcp_app.lifespan (unified)
        └── dispose_engine() on exit

Mounted sub-servers (direct mode - no lifespan overhead):
  ├── sensei-core (no lifespan)
  ├── scout (no lifespan)
  ├── kura (no lifespan - CHANGED)
  └── tome (no lifespan - CHANGED)
```

### Unified MCP Lifespan

```python
@asynccontextmanager
async def lifespan(server):
    try:
        yield
    finally:
        await dispose_engine()
```

### Sub-Server Lifespans

Removed entirely. Benefits:
- FastMCP uses direct mounting (faster)
- No duplicate `ensure_db_ready()` calls
- Disposal handled by parent (unified) lifespan

## File Changes

### Delete/Gut

**`sensei/database/local.py`** - Remove:
- Entire module (no lifecycle or migration helpers remain)

**`sensei/paths.py`** - Remove:
- `get_pgdata()`
- `get_pg_log()`
- `get_local_database_url()`

**`tests/test_database_local.py`** - Delete or reduce significantly

### Modify

**`sensei/settings.py`**:
- Remove `is_external_database` property
- Make `database_url` required (no default)

**`sensei/unified.py`**:
- Remove `ensure_db_ready()` import and call
- Keep `dispose_engine()` in finally

**`sensei/kura/server.py`**:
- Remove entire `lifespan` function
- Remove `lifespan=lifespan` from FastMCP constructor

**`sensei/tome/server.py`**:
- Remove entire `lifespan` function
- Remove `lifespan=lifespan` from FastMCP constructor

**`scripts/ingest.py`**:
- Remove `ensure_db_ready()` import and call

**`tests/test_paths.py`**:
- Remove tests for deleted path functions

## Developer Experience

### Local Development Flow

```bash
# 1. Start PostgreSQL
brew services start postgresql@17
# or: docker-compose up -d postgres

# 2. Create database
createdb sensei

# 3. Provide SENSEI_DATABASE_URL via runtime configuration
# Example value: postgresql+asyncpg://localhost/sensei

# 4. Run migrations
alembic upgrade head

# 5. Run sensei
python -m sensei          # unified MCP (stdio)
python -m sensei.api      # REST API + MCP
python -m sensei.tome     # tome standalone
```

### Error Messages

| Condition | Error |
|-----------|-------|
| SENSEI_DATABASE_URL not set | `pydantic_settings.SettingsError: SENSEI_DATABASE_URL required` |
| Database unavailable | `sqlalchemy.exc.OperationalError: connection refused` |
| Migrations not run | `sqlalchemy.exc.ProgrammingError: relation "queries" does not exist` |

All clear, actionable errors. No magic.

### Production (Fly.io)

Unchanged. Already uses:
- External SENSEI_DATABASE_URL pointing to Cloud SQL
- Explicit migration in deploy script: `alembic upgrade head`

## Benefits

1. **Simpler mental model**: One mode, explicit everything
2. **Faster sub-servers**: Direct mounting (no lifespan overhead)
3. **No idempotency hacks**: No `_db_ready` flag needed
4. **Clearer errors**: Standard SQLAlchemy/Pydantic errors
5. **Less code**: ~150 lines removed from database/local.py
