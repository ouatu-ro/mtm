# Plan: Debugger Facts/Presentation Rewrite

## Goal

Replace the debugger's string-first session/rendering surface with a fact/query
presentation stack while preserving raw trace semantics and the interactive
command set.

## Scope

In scope:
- Keep `mtm/debugger/trace.py` as the execution/history anchor.
- Remove the current `render.py`-centered string-first architecture.
- Introduce a custom in-memory fact/query layer behind clean interfaces.
- Introduce a shared block-oriented presentation model and presenter.
- Replace plain-text debugger rendering with a renderer that consumes the
  presentation model.
- Rewrite session and shell around mutation/query/presenter boundaries.
- Rewrite debugger-focused tests to match the new architecture.

Out of scope:
- Datalog/Cozo integration.
- New debugger commands or breakpoint semantics.
- Artifact/raw debugger initialization.
- Full ANSI color restoration in the first replacement pass.

## Assumptions

- Existing `RawTraceRunner` grouped-step and source-map semantics are correct
  enough to preserve.
- The first pass can rebuild debugger read views from Python facts/queries
  without introducing persistence.
- Plain-text parity is more important than keeping the current renderer internals
  or test surface.

## Steps

- [ ] S1: Create the replacement scaffolding and remove the string-first
  renderer/session coupling.
- [ ] S2: Port debugger commands onto facts, queries, presentation blocks, and
  text rendering.
- [ ] S3: Rewrite debugger tests around trace behavior, queries, presenter, text
  rendering, and shell wiring.
- [ ] S4: Run focused and repo-level validation, update docs/exports, and remove
  obsolete debugger modules/helpers.

## Validation

- Typecheck: Not available as a standalone repo-native command today.
- Lint: No dedicated repo-native lint command identified yet.
- Tests:
  - `uv run pytest -q tests/test_raw_trace.py`
  - `uv run pytest -q tests/test_cli_debugger.py tests/test_debugger_session.py tests/test_debugger_shell.py`
  - `uv run pytest -q`
- Final checks:
  - `git diff --check`
  - debugger CLI smoke checks if the rewritten shell lands

## Progress Log

- 2026-05-05 17:37: Plan created.

## Findings / Debt

- [ ] D1: ANSI rendering is coupled to the old text-first renderer surface.
  Impact: color may need to be temporarily simplified or deferred during the
  replacement.
  Recommendation: delay until plain-text renderer and help metadata stabilize.

## Completion Criteria

- Debugger rendering no longer depends on `render.py` summaries/helpers from
  session code.
- Session APIs are mutation/query-oriented rather than text-oriented.
- A fact/query layer exists and backs debugger read views.
- A shared presentation model exists and is consumed by the text renderer.
- Debugger tests cover the new architecture instead of the old helper internals.
