# Plan: Documentation Restructure

## Goal

Move MTM documentation into a conventional `docs/` structure with clear reader
intent:

- specs describe contracts and intended behavior
- architecture explains how implementation pieces fit
- runbooks give reproducible command sequences
- results preserve measurements and observations
- tools describe local helper programs
- RFCs capture proposals and direction
- user guides explain how to use the project

The first pass should be mostly mechanical: move or copy existing text into
better homes, update links, and avoid rewriting content while migrating.

The docs should also be ready for a small static documentation website. Markdown
remains canonical; any website layer is only a reader-friendly presentation
around those files.

## Target Structure

```text
docs/
  index.md

  user-guide/
    cli.md
    debugger.md

  specs/
    spec.md
    overview.md
    object-model.md
    abi-and-artifacts.md
    meta-asm-and-lowering.md
    recursive-towers.md
    invariants-and-correctness.md

  architecture/
    debugger-stepper.md

  runbooks/
    l2-incrementer.md

  results/
    index.md
    l2-bootstrap.md

  tools/
    index.md
    trace-viewer.md
    c-runners.md

  rfc/
    help-menu.md

mkdocs.yml              # optional site shell, added after markdown migration
```

Root-level `README.md` should stay small: project identity, high-level
intuition, one compact pipeline diagram, one happy-path command sequence, and
links into `docs/`.

Do not keep both `docs/` and `documentation/` long term. Use `docs/` as the
canonical directory.

## Scope

In scope:

- Move existing root/spec-like docs into `docs/specs/`.
- Split the current monolithic spec into first-pass concern files.
- Move existing debugger specs/runbooks/results to the target directories.
- Add `docs/index.md` as the docs map.
- Add `docs/tools/*` pages that describe existing helper tools.
- Update in-repo links to the new paths.
- Add root stubs only if old paths are likely to be referenced externally.
- Add lightweight YAML front matter to migrated pages.
- Add an optional MkDocs Material site shell after the Markdown structure is
  stable, using a pinned project dev dependency instead of an ad hoc `uvx`
  dependency.

Out of scope:

- Rewriting the technical content while migrating.
- Changing code, CLI behavior, tests, tools, generated artifacts, C runners, or
  HTML tooling.
- Renaming tool source files.
- Turning docs into a bespoke documentation app.
- Adding Rich/color help rendering.
- Publishing or deploying a documentation website.

## Current Source Files

Existing documentation-like files:

```text
docs/debugger-presentation-spec.md
docs/debugger-repl-spec.md
docs/debugger-stepper.md
docs/help-menu-rfc.md
docs/l2-bootstrap-results.md
docs/l2-incrementer-runbook.md
documentation/OBJECT_MODEL.md
documentation/Spec.md
documentation/DOCS-SCRATCHPAD.MD
```

Existing tool files to document but not modify:

```text
tools/trace-viewer.html
tools/assets/incrementer-raw-trace.js
tools/assets/right-left-walk.tm
tools/assets/right_left_walk_tm.py
tools/generate_l1_raw_guest_data.py
tools/generate_l2_meta_asm_data.py
tools/generate_raw_tm_runner_data.py
tools/generate_raw_tm_c.py
tools/l1_raw_guest_runner.c
tools/l2_meta_asm_runner.c
tools/raw_tm_runner.c
```

## Mechanical Mapping

Move/copy with minimal edits:

```text
documentation/OBJECT_MODEL.md
  -> docs/specs/object-model.md

docs/debugger-stepper.md
  -> docs/architecture/debugger-stepper.md

docs/debugger-presentation-spec.md
  -> docs/specs/debugger-presentation.md

docs/debugger-repl-spec.md
  -> docs/specs/debugger-repl.md

docs/l2-incrementer-runbook.md
  -> docs/runbooks/l2-incrementer.md

docs/l2-bootstrap-results.md
  -> docs/results/l2-bootstrap.md

docs/help-menu-rfc.md
  -> docs/rfc/help-menu.md

documentation/DOCS-SCRATCHPAD.MD
  -> docs/index.md for the landing-page explanation
  -> docs/specs/overview.md for reusable pipeline/architecture text
```

Create as indexes/summaries:

```text
docs/index.md
docs/specs/spec.md
docs/results/index.md
docs/tools/index.md
docs/tools/trace-viewer.md
docs/tools/c-runners.md
docs/user-guide/cli.md
docs/user-guide/debugger.md
```

Split `documentation/Spec.md` into:

```text
Section 1 Goal
  -> docs/specs/overview.md

Section 2 Public Interface
  -> docs/specs/overview.md
  -> docs/specs/object-model.md where object/API-specific

Section 3 Source Program and Band
  -> docs/specs/object-model.md

Section 4 ABI and Encoding
  -> docs/specs/abi-and-artifacts.md

Section 5 Semantic UTM Object
  -> docs/specs/object-model.md

Section 6 .utm.band Artifact Layout
  -> docs/specs/abi-and-artifacts.md

Section 7 Meta-ASM
  -> docs/specs/meta-asm-and-lowering.md

Section 8 Meta-ASM Instruction Set
  -> docs/specs/meta-asm-and-lowering.md

Section 9 Universal Interpreter Program
  -> docs/specs/meta-asm-and-lowering.md

Section 10 Lowering to .tm
  -> docs/specs/meta-asm-and-lowering.md

Section 11 Artifact Naming / Tower
  -> docs/specs/recursive-towers.md

Section 12 Lowering Sketches
  -> docs/specs/meta-asm-and-lowering.md

Section 13 Runtime Alphabet
  -> docs/specs/invariants-and-correctness.md
  -> docs/specs/abi-and-artifacts.md if artifact-format-specific

Section 14 Correctness Targets
  -> docs/specs/invariants-and-correctness.md

Section 15 Milestones and Results
  -> docs/results/index.md
  -> link to docs/results/l2-bootstrap.md
```

## Do Not Rewrite In First Pass

Preserve wording unless needed for path changes in:

- `documentation/OBJECT_MODEL.md`
- `documentation/Spec.md` section bodies
- `documentation/DOCS-SCRATCHPAD.MD`
- `docs/debugger-presentation-spec.md`
- `docs/debugger-repl-spec.md`
- `docs/debugger-stepper.md`
- `docs/l2-incrementer-runbook.md`
- `docs/l2-bootstrap-results.md`

Allowed minimal edits during migration:

- update headings to match new file names
- add YAML front matter for `title`, `description`, `status`, and `audience`
- add a one-paragraph purpose note at the top of a new index file
- add "Moved to ..." stubs for old paths if keeping compatibility
- update relative links
- fix references from `documentation/` to `docs/`
- add short metadata such as "Status: current spec", "Status: runbook", or
  "Status: RFC"

Do not modify:

- `tools/*.py`
- `tools/*.c`
- `tools/*.html`
- `tools/assets/*`
- tests
- package metadata
- generated artifacts

## Assumptions

- `docs/` is the canonical documentation directory.
- `documentation/` is temporary or user-created draft space and should not be
  the final public docs root.
- Existing doc content is more valuable than perfect prose in the migration
  commit.
- `docs/results/l2-bootstrap.md` should preserve the existing narrative and not
  be duplicated.
- MkDocs Material should be added as a pinned dev dependency in `pyproject.toml`
  and `uv.lock`, rather than invoked as an unpinned external tool.
- `docs/specs/results.md` is not needed in the first-pass structure; use
  `docs/results/index.md` instead.
- MkDocs Material is the preferred site wrapper if/when a website is added,
  because it keeps Markdown as source of truth and provides navigation/search
  without a custom frontend.
- Arbitrary YAML front matter keys may not render automatically in MkDocs, but
  they are useful for future templates/plugins and page classification.

## Front Matter Policy

Use concise YAML front matter on migrated pages:

```md
---
title: Object Model
description: Core MTM semantic objects and artifact wrappers.
status: current
audience: engineer
---
```

Suggested `status` values:

- `current`
- `runbook`
- `results`
- `rfc`
- `experimental`

Suggested `audience` values:

- `user`
- `engineer`
- `maintainer`

Do not spend the first pass tuning metadata. Add enough to support navigation,
search summaries, and future site rendering.

## Steps

- [x] S1: Inspect and stabilize current doc state.
  Decide whether `documentation/Spec.md`, `documentation/OBJECT_MODEL.md`, and
  `documentation/DOCS-SCRATCHPAD.MD` are drafts, moves, or canonical source
  files before moving anything.

- [x] S2: Create target directories and move existing whole-file docs.
  Move debugger specs, debugger architecture notes, runbooks, results, and RFCs
  to their target directories with only heading/link/status adjustments.

- [x] S3: Split `documentation/Spec.md` mechanically.
  Create the first-pass spec files under `docs/specs/` by copying the mapped
  sections. Do not rewrite content beyond path references and headings.

- [x] S4: Create indexes and tool docs.
  Add `docs/index.md`, `docs/specs/spec.md`, `docs/results/index.md`,
  `docs/tools/index.md`, `docs/tools/trace-viewer.md`,
  `docs/tools/c-runners.md`, and user-guide entrypoints.

- [x] S5: Update links and root entrypoints.
  Update references to moved docs. Keep or add root stubs only if old root paths
  are still useful compatibility targets.

- [x] S6: Validate and clean up migration debris.
  Check for broken in-repo links, stale `documentation/` references, duplicate
  docs, accidental code/tool drift, and generated cache files.

- [ ] S7: Add MkDocs site shell.
  Add `mkdocs.yml` with navigation matching the `docs/` structure. Prefer
  MkDocs Material, Mermaid support, and plain Markdown pages. Add MkDocs
  Material as a pinned dev dependency. Do not add custom frontend code.

- [ ] S8: Adapt scratchpad into the docs landing page.
  Use `documentation/DOCS-SCRATCHPAD.MD` as the seed for `docs/index.md` or
  `docs/specs/overview.md`, preserving the high-level explanation and staged
  pipeline diagrams while linking to deeper pages.

- [ ] S9: Verify local site navigation.
  Run the chosen MkDocs preview/build command, confirm navigation/search works,
  and record any plugin or dependency choices. Do not add publish automation in
  this step.

## Validation

- Typecheck: not applicable for doc-only migration.
- Lint: not configured.
- Tests: not required unless CLI docs or examples are changed.
- Final checks:
  - `git diff --check`
  - `rg -n "documentation/|Spec.md|OBJECT_MODEL.md|debugger-repl-spec|l2-incrementer-runbook" docs README.md README.MD plans || true`
  - `find docs -maxdepth 3 -type f | sort`
  - `git status --short --untracked-files=all`

If examples are edited:

- `uv run mtm -h`
- `uv run mtm compile -h`
- `uv run mtm trace -h`
- `uv run mtm dbg -h`

If the optional site shell is added:

- `uv run mkdocs build --strict`

## Progress Log

- 2026-05-06 19:47: Plan created. No implementation performed and no commit
  made, per request.
- 2026-05-06 19:55: Added optional MkDocs/static-site steps and front matter
  policy. No implementation performed and no commit made, per request.
- 2026-05-06 19:57: Clarified scratchpad extraction mapping and switched the
  site-shell validation path to a pinned project dev dependency.
- 2026-05-06 20:00: Completed S1/S2 inventory and move pass. Moved
  `docs/debugger-stepper.md`, `docs/debugger-presentation-spec.md`,
  `docs/debugger-repl-spec.md`, `docs/l2-incrementer-runbook.md`,
  `docs/l2-bootstrap-results.md`, `docs/help-menu-rfc.md`, and
  `documentation/OBJECT_MODEL.md` into the target `docs/` subdirectories;
  `documentation/Spec.md` and `documentation/DOCS-SCRATCHPAD.MD` were left
  in place for later steps.
- 2026-05-06 20:10: Completed S3 mechanical split. Created
  `docs/specs/overview.md`, `docs/specs/abi-and-artifacts.md`,
  `docs/specs/meta-asm-and-lowering.md`,
  `docs/specs/recursive-towers.md`, and
  `docs/specs/invariants-and-correctness.md` from `documentation/Spec.md`
  with front matter and top headings; validation passed with `git diff --check`,
  `find docs/specs -maxdepth 1 -type f | sort`,
  `rg -n "^## [0-9]+\\." docs/specs || true`, and
  `git status --short --untracked-files=all`.
- 2026-05-06 20:04: Completed S4 navigational docs. Added
  `docs/index.md`, `docs/specs/spec.md`, `docs/results/index.md`,
  `docs/tools/index.md`, `docs/tools/trace-viewer.md`,
  `docs/tools/c-runners.md`, `docs/user-guide/cli.md`, and
  `docs/user-guide/debugger.md`; validation passed with `git diff --check`,
  `find docs -maxdepth 3 -type f | sort`,
  `rg -n "tools/trace-viewer.html|tools/l1_raw_guest_runner.c|docs/specs/spec.md|docs/tools" docs plans/docs-restructure.md`,
  and `git status --short --untracked-files=all`.
- 2026-05-06 20:15: Completed S5 entrypoint cleanup. Added a compact root
  `README.md` that links to `docs/index.md`, and added a tiny canonical-path
  notice to `documentation/Spec.md`. Validation passed with `git diff --check`,
  `rg -n "documentation/|Spec.md|OBJECT_MODEL.md|debugger-repl-spec|l2-incrementer-runbook|l2-bootstrap-results|debugger-stepper.md|help-menu-rfc" docs README.md documentation plans/docs-restructure.md || true`,
  `find docs -maxdepth 3 -type f | sort`, and
  `git status --short --untracked-files=all`.
- 2026-05-06 20:18: Completed S6 validation sweep. `git diff --check` passed,
  `git status --short --untracked-files=all` was clean, stale-path search found
  only historical plan references, and `git check-ignore -v tools/__pycache__
  mtm/__pycache__ examples/__pycache__ tests/__pycache__` confirmed Python
  cache directories are ignored.

## Findings / Debt

- [ ] D1: Existing `documentation/` directory conflicts with canonical `docs/`
  target.
  Impact: Keeping both roots will confuse readers and link maintenance.
  Recommendation: Resolve during S1 by choosing whether `documentation/` files
  are drafts to move into `docs/` or temporary files to remove after migration.

- [ ] D2: Tool docs do not currently exist as first-class documentation.
  Impact: The trace viewer and C runner experiments are discoverable only by
  reading tools or runbooks.
  Recommendation: Add concise `docs/tools/*` pages in S4, with commands
  delegated to runbooks.

- [x] D3: `tools/__pycache__` appeared during inventory.
  Impact: Generated Python cache files should not be documented or committed.
  Resolved: S6 confirmed `tools/__pycache__` and other Python cache directories
  are ignored by `.gitignore`; no tracked cleanup was needed.

- [ ] D4: Documentation website dependencies are undecided.
  Impact: Adding MkDocs can be done via `uvx` with no repo dependency, or as a
  project dev dependency for repeatability.
  Recommendation: Resolve during S7 by adding a pinned project dev dependency
  and validating with `uv run mkdocs build --strict`.

## Completion Criteria

- All current documentation lives under the target `docs/` structure.
- `documentation/` is either gone or explicitly treated as scratch/draft space.
- Root README links to `docs/index.md` and does not embed full specs.
- `docs/specs/spec.md` is a clear index to split spec files.
- Runbooks, results, tools docs, RFCs, specs, and architecture docs are visibly
  separated.
- Existing technical wording is preserved during the migration except for
  headings, metadata, and links.
- Optional MkDocs site shell exists only after Markdown docs are stable.
- Front matter is present on migrated pages with at least `title`, `status`,
  and `audience` where useful.
- Validation commands pass or skipped checks are explicitly recorded.
