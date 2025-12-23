# Simplify Database Lifecycle (Sensei)

This ExecPlan is a living document. The sections Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective must be kept up to date as work proceeds.

This plan must be maintained in accordance with .agent/PLANS.md at the repository root.

## Purpose / Big Picture

After this change, Sensei no longer auto-manages PostgreSQL or auto-runs migrations on startup. Database lifecycle becomes explicit: the application expects a database URL at startup and fails fast if it is missing or the database is unavailable. Sub-servers no longer incur lifecycle overhead, and engine cleanup remains centralized in the unified server lifespan. Success is demonstrated by running the servers without automatic initialization logic and by tests that no longer reference removed lifecycle helpers.

## Progress

- [x] (2025-12-21 10:00Z) Removed PostgreSQL path helpers from sensei/paths.py and updated tests accordingly.
- [x] (2025-12-21 10:10Z) Required database_url in sensei/settings.py and removed is_external_database.
- [x] (2025-12-21 10:20Z) Removed sensei/database/local.py entirely after dropping lifecycle and migration helpers.
- [x] (2025-12-21 10:30Z) Simplified unified lifespan and removed sub-server lifespans (kura, tome); removed ingest ensure_db_ready.
- [x] (2025-12-21 10:40Z) Updated tests for the new lifecycle and refreshed README to reflect explicit setup.

## Surprises & Discoveries

- Observation: Standardizing on SENSEI_DATABASE_URL made aliasing unnecessary once env_prefix was retained.
  Evidence: database_url is now required with no alias configuration.

## Decision Log

- Decision: Keep SenseiSettings env_prefix and require SENSEI_DATABASE_URL only.
  Rationale: Align configuration naming with the project’s conventions and remove ambiguity.
  Date/Author: 2025-12-21 / Codex

- Decision: Remove sensei/database/local.py after standardizing on explicit CLI migrations.
  Rationale: Keeping a programmatic helper was unnecessary once migrations are handled explicitly outside the app.
  Date/Author: 2025-12-21 / Codex

## Outcomes & Retrospective

The lifecycle refactor removed implicit PostgreSQL management and centralized cleanup to engine disposal. Tests and docs reflect explicit database setup, and sub-servers no longer carry lifespans solely for initialization. Remaining follow-up is to run the test suite in an environment with a configured database URL to confirm runtime behavior.

## Context and Orientation

The database engine is configured in sensei/database/engine.py and consumed by storage helpers in sensei/database/storage.py. Migrations are configured via sensei/migrations/env.py and can be run through alembic. The unified MCP server is defined in sensei/unified.py and mounted into the REST API in sensei/api/__init__.py. Sub-servers live under sensei/kura and sensei/tome. The path helpers are in sensei/paths.py, and tests live under tests/ with a shared tests/conftest.py fixture for database setup.

## Plan of Work

First, remove PostgreSQL-specific path helpers from sensei/paths.py and delete the corresponding tests. Then make database_url required in sensei/settings.py and remove is_external_database, requiring SENSEI_DATABASE_URL via the settings prefix. Next, remove sensei/database/local.py entirely to eliminate lifecycle and migration helpers. Simplify the unified lifespan to only dispose the engine and remove sub-server lifespans from kura and tome; remove ensure_db_ready from the ingest script. Finally, update tests to align with the new lifecycle and update README.md to describe explicit migration requirements without mentioning auto-managed PostgreSQL.

## Concrete Steps

Work from the repository root. Edit the following files in order:

  - sensei/paths.py: remove get_pgdata, get_pg_log, and get_local_database_url.
  - sensei/settings.py: require database_url and remove is_external_database (SENSEI_DATABASE_URL only).
  - sensei/database/local.py: remove the module entirely.
  - sensei/unified.py: remove ensure_db_ready usage; keep dispose_engine in finally.
  - sensei/kura/server.py and sensei/tome/server.py: remove lifespan functions and constructor parameters.
  - scripts/ingest.py: remove ensure_db_ready import and call.
  - tests/test_paths.py and tests/test_database_local.py: remove tests tied to deleted helpers.
  - tests/conftest.py: ensure the database URL is provided for settings during tests.
  - README.md: replace auto-managed PostgreSQL note with explicit migration requirement.

To run the test suite after changes, execute:

  uv run pytest

## Validation and Acceptance

The application should import without referencing ensure_db_ready, and the unified MCP server lifespan should only dispose the engine. Kura and Tome servers should instantiate FastMCP without a lifespan. Running the test suite should pass with SENSEI_DATABASE_URL configured; tests should no longer reference removed path helpers or PostgreSQL lifecycle functions. README should no longer claim that Sensei manages local PostgreSQL.

## Idempotence and Recovery

These edits are safe to repeat. If a change introduces an import error, restore the last working version of the file and re-apply edits in smaller increments. No destructive database operations are performed by this plan.

## Artifacts and Notes

Key excerpts after completion:

  sensei/unified.py lifespan yields without initialization and disposes the engine in finally.

## Interfaces and Dependencies

The main interfaces affected are:

  - sensei.settings.SenseiSettings.database_url: required field, reads SENSEI_DATABASE_URL.
  - sensei.database.engine.dispose_engine(): called by unified lifespan on shutdown.

These depend on alembic, sqlalchemy, and pydantic-settings. No new dependencies are introduced.

Plan update note: Removed database/local.py and its tests after confirming migrations are explicit via CLI, and updated the plan to match.
