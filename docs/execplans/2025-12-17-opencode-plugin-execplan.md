# Implement Sensei OpenCode plugin

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository contains the ExecPlan requirements in `.agent/PLANS.md`. This document must be maintained in accordance with that file.

## Purpose / Big Picture

Enable OpenCode users to access Sensei’s documentation research via two custom tools (`sensei_query`, `sensei_feedback`) and an optional plugin (`sensei`) that automatically prompts the agent to rate Sensei responses when a session becomes idle.

Success looks like:

- An OpenCode user can drop the shipped `.ts` files into `~/.config/opencode/tool/` and `~/.config/opencode/plugin/`.
- OpenCode can call `sensei_query` to POST to Sensei’s REST API `/query` and returns markdown that includes a machine-readable query id.
- When the agent finishes (session becomes idle), the `sensei` plugin prompts the agent to call `sensei_feedback` with ratings for the captured query id.
- `sensei_feedback` POSTs to Sensei’s REST API `/rate` and returns a confirmation string.

## Progress

- [x] (2025-12-17 22:56Z) Kick off implementation work; confirm OpenCode plugin/tool locations and hook names from upstream docs.
- [x] (2025-12-17 23:11Z) Add `docs/execplans/2025-12-17-opencode-plugin-execplan.md` and keep it current while implementing.
- [x] (2025-12-17 23:11Z) Implement `packages/sensei-opencode/` package layout and versioning.
- [x] (2025-12-17 23:11Z) Implement `sensei_query` and `sensei_feedback` OpenCode tools.
- [x] (2025-12-17 23:11Z) Implement `sensei` OpenCode plugin: capture query ids and prompt for ratings on `session.idle`.
- [x] (2025-12-17 23:11Z) Add installer artifact(s): a portable shell script and an HTTP endpoint to serve it from the Sensei API.
- [ ] Validate locally (format/typecheck/tests) and close beads for completed tasks.

## Surprises & Discoveries

- Observation: OpenCode supports both plugins and standalone custom tools; tools live in `.opencode/tool/` or `~/.config/opencode/tool/`, plugins live in `.opencode/plugin/` or `~/.config/opencode/plugin/`.
  Evidence: https://opencode.ai/docs/plugins/ and https://opencode.ai/docs/custom-tools/
- Observation: The OpenCode SDK has a `noReply` option for `session.prompt`; `noReply: true` creates context without running the model, while default triggers the model and returns an assistant message.
  Evidence: https://opencode.ai/docs/sdk/
- Observation: Plugin hook payloads include `sessionID` and `callID`, and `tool.execute.after` provides the tool result as `output.output` (string).
  Evidence: https://github.com/sst/opencode/blob/dev/packages/plugin/src/index.ts

## Decision Log

- Decision: Store Sensei connection settings in a small JSON config file (searched in project `.opencode/` and then `~/.config/opencode/`) instead of requiring environment variables.
  Rationale: Project instructions forbid suggesting env var changes; a file keeps install UX simple and works cross-shell.
  Date/Author: 2025-12-17 / Codex
- Decision: Encode query id in a machine-readable HTML comment marker appended to the tool output.
  Rationale: Avoid brittle regex over natural-language output; marker parsing is a simple, deterministic extraction method for the plugin.
  Date/Author: 2025-12-17 / Codex

## Outcomes & Retrospective

To be completed after implementation.

## Context and Orientation

Sensei is primarily a Python project with a FastAPI REST server in `sensei/api/__init__.py`. The REST API currently exposes:

- `POST /query` returning `{ query_id, output }`
- `POST /rate` accepting `{ query_id, correctness, relevance, usefulness, reasoning?, agent_*? }`
- `GET /health`

OpenCode supports:

- Custom tools as `.ts`/`.js` files in `.opencode/tool/` (project) or `~/.config/opencode/tool/` (global).
- Plugins as `.ts`/`.js` files in `.opencode/plugin/` (project) or `~/.config/opencode/plugin/` (global).

This change adds a new package under `packages/sensei-opencode/` that contains the files intended for distribution (via npm/unpkg and/or a simple installer script).

## Plan of Work

Create a new workspace package `packages/sensei-opencode/` that contains:

- `dist/tool/sensei_query.ts` and `dist/tool/sensei_feedback.ts`: OpenCode custom tools that call the Sensei REST API.
- `dist/plugin/sensei.ts`: OpenCode plugin that listens for `tool.execute.after` to capture the last query id produced by `sensei_query` and listens for `session.idle` to prompt the agent to rate the response using `sensei_feedback`.
- `dist/install.sh`: a portable installer that copies/downloads the three `.ts` files to the user’s `~/.config/opencode/` directories and writes a small `~/.config/opencode/sensei.json` config file if needed.

Update the Sensei REST server to serve the installer script at `GET /opencode` so the published service can support a one-liner installer. The HTTP handler should return a `text/plain` shell script body.

## Concrete Steps

From repository root:

1. Create `packages/sensei-opencode/` and its `dist/` tree.
2. Implement the tool and plugin files.
3. Implement a minimal installer script and wire it into `sensei/api/__init__.py` as `GET /opencode`.
4. Run repo checks:

   - `npm run check`
   - `uv run pytest -q` (or the project’s standard test command)

## Validation and Acceptance

Acceptance is met when:

- The new files exist at the expected paths.
- The Sensei API server includes `GET /opencode` and returns a non-empty shell script.
- Typechecking and tests pass locally.
- The OpenCode plugin logic is safe against infinite prompting loops (a rating prompt should not trigger itself repeatedly on subsequent `session.idle` events).

## Idempotence and Recovery

The installer script should be safe to re-run: it should overwrite the installed `.ts` files and update the config file only if missing or explicitly confirmed.

If the OpenCode plugin causes repeated prompts, disable it by removing `~/.config/opencode/plugin/sensei.ts` or commenting out the `session.idle` hook until the loop guard is fixed.

## Artifacts and Notes

Upstream OpenCode docs used during implementation:

- Plugins: https://opencode.ai/docs/plugins/
- Custom tools: https://opencode.ai/docs/custom-tools/
- SDK: https://opencode.ai/docs/sdk/
