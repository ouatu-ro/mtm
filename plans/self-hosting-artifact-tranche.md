# Plan: Self-Hosting Artifact Tranche

## Goal

Make the artifact contract honest and unlock the first recursive self-hosting
workflow without blocking on an ABI-only universal host redesign.

By the end of this tranche, the project should support:

- `.tm` artifacts that optionally persist `target_abi` / `minimal_abi`
- compatibility checks between `.tm` and `.utm.band` when both carry ABI data
- a serializable source artifact format
- a shared `RawTMInstance` object for raw execution and recursive guest input
- a raw-guest compiler path
- explicit `l1` / `l2` artifact production in the CLI

## Scope

In scope:

- Shared ABI literal serialization and compatibility helpers.
- Backward-compatible `.tm` ABI metadata persistence.
- Compiler correctness fixes for endpoint resolution, blank consistency, and ABI grammar/version validation.
- Runtime artifact compatibility checks that do not make raw execution ABI-dependent.
- `TMTransitionProgram.transitions` as a read-only alias over `prog`.
- A safe literal-assignment source artifact format, working name `*.mtm.source`.
- Raw-guest ABI/encoding inference that supports `L`, `S`, and `R`.
- Raw-guest compilation from `RawTMInstance` to `UTMBandArtifact`.
- CLI workflows for producing `l1` and `l2` artifacts.

Out of scope:

- Redesigning `UniversalInterpreter` to be ABI-only rather than encoding-specialized.
- Replacing raw run-result dictionaries with a typed `RunResult`.
- Adding `artifact.decoded_view()` convenience APIs.
- Persisting source-map or debugger metadata in `.tm`.
- Broad debugger or presentation-layer refactors.

## Assumptions

- `.utm.band` owns concrete `Encoding` because it describes how to decode that input band.
- `.tm` may carry ABI metadata for compatibility/provenance, but raw execution must not depend on ABI or `Encoding`.
- For `l2`, the raw guest's ABI metadata must describe the raw guest being encoded. The compiler MAY infer a minimal ABI from the raw guest program and tape, or MAY accept an explicit target ABI large enough to encode it. It must NOT blindly inherit ABI metadata from the `l1` `.tm` or `.utm.band`.
- `minimal_abi`, when persisted for a raw guest, should be inferred from the raw guest.
- `target_abi` may be user-specified or selected by policy, but it must be validated against the raw guest.
- Source `TMProgram` remains source-level and may continue to reject `S`; raw-guest support for `S` belongs on the raw path.
- `RawTMInstance` is the single object shape for raw program plus tape/head/state. Do not add a duplicate `RawGuestInstance`.

## Steps

- [x] S1: Add shared ABI literal and compatibility helpers.
  Deliverables: `abi_to_literal`, `abi_from_literal`, `abi_compatible`, `assert_abi_compatible`; `.utm.band` and `.tm` artifact code use the same ABI literal path; `.tm` ABI parsing does not depend on an `Encoding` fallback.
  Validation: ABI literal round-trip tests; matching and mismatched compatibility helper tests.

- [x] S2: Make `.tm` metadata honest and usable.
  Deliverables: `UTMProgramArtifact.write(...)` emits `target_abi` / `minimal_abi` when known; `UTMProgramArtifact.read(...)` returns persisted metadata or `None`; `read_tm(path) -> TMTransitionProgram` and `TMTransitionProgram.write(...)` remain raw-only.
  Validation: old `.tm` artifacts still read; new round-trip tests cover `.tm` with and without ABI metadata.

- [x] S3: Fix compiler correctness gaps.
  Deliverables: endpoint fallback order is `TMInstance`, then `TMProgram`, then `Compiler`; instance values override program values; compilation rejects `TMProgram.blank != SourceTape.blank`; ABI validation checks `state_width`, `symbol_width`, `dir_width`, and `grammar_version`.
  Validation: targeted compiler tests for all endpoint sources, blank mismatch, and grammar-version mismatch.

- [x] S4: Add artifact compatibility checks at run time.
  Deliverables: `UTMProgramArtifact.run(...)` checks `.tm` versus `.utm.band` compatibility only when both carry `target_abi`; incompatible grammar/version or width mismatches fail before execution; missing `.tm` ABI metadata still allows execution; CLI `run` preserves program-side ABI metadata instead of copying band ABI onto the program artifact.
  Validation: tests cover compatible metadata, incompatible metadata, missing `.tm` metadata, and CLI `run` metadata preservation.

- [x] S5: Add `TMTransitionProgram.transitions`.
  Deliverables: read-only `transitions` alias over `prog`.
  Validation: existing raw transition tests still pass; docs can refer to `transitions` without lying.

- [x] S6: Introduce a serializable source artifact.
  Deliverables: safe literal-assignment `*.mtm.source` artifact containing `TMProgram`, `SourceTape`, `initial_state`, `halt_state`, and optional `name` / `note`; parser uses literal evaluation and no `run_path`; CLI can emit source artifact from `.py`.
  Validation: source artifact read/write round-trip test; CLI source emission test.

- [x] S7: Rename/generalize `TMRunConfig` to `RawTMInstance`.
  Deliverables: one raw program-plus-state object for both raw execution and recursive guest compilation; `UTMBandArtifact.to_raw_instance(...)`; compatibility alias for current `to_run_config(...)` callers.
  Validation: `uv run pytest -q`; `git diff --check`.
  Commit: `85d74c8`.

- [x] S8: Add raw-guest ABI and encoding inference.
  Deliverables: infer minimal `TMAbi` from `RawTMInstance.program.start_state`, `program.halt_state`, current `state`, all transition source/target states, program alphabet, program blank, transition read/write symbols, concrete tape symbols, and raw directions actually used; support raw directions including `S`; add a helper such as `build_raw_guest_encoding(...)`.
  Validation: raw-guest encoding tests with `S`; inferred `dir_width` tests when `S` is present; host dispatch test that intentionally treats neither `L` nor `R` as stay-put.

- [x] S9: Implement the raw-guest compiler path.
  Deliverables: compile `RawTMInstance -> UTMEncoded -> UTMBandArtifact`; raw guest tape conversion mirrors `SourceTape.from_dict(...)` semantics, with negative addresses on `left_band`, nonnegative addresses on `right_band`, and the current head cell included even if blank.
  Validation: trivial `TMTransitionProgram` guest compiles into `.utm.band`; resulting band is runnable by a lowered host.

- [x] S10: Add the `l1` / `l2` CLI workflow.
  Deliverables: CLI can produce `incrementer.mtm.source`, `incrementer.l1.utm.band`, `incrementer.l1.tm`, `incrementer.l2.utm.band`, and `incrementer.l2.tm`; `l1` means one UTM layer over the original source guest; `l2` means one UTM layer over the `l1` raw host computation as guest.
  Validation: CLI tests for `l1` and `l2` artifact generation; bounded-fuel execution of `l2` artifacts without artifact, compatibility, or decode errors.

## Validation

- Typecheck: not currently configured.
- Lint: `git diff --check`
- Focused tests: run targeted `uv run pytest -q ...` commands per step.
- Tests: `uv run pytest -q`
- Final checks: `git status --short`; representative CLI smoke for `l1`, `l2`, and artifact `run` paths.

## Progress Log

- 2026-05-05 19:20 EEST: Committed S7 as `85d74c8`. Validation: `uv run pytest -q`; `git diff --check`.
- 2026-05-05 19:20 EEST: Restyled plan as a durable execute-disk-plan artifact.
- 2026-05-05 19:26 EEST: Completed S1. Added shared ABI literal and compatibility helpers in `mtm/source_encoding.py`, updated `.utm.band` artifact IO to use them, and added focused helper tests. Validation: `uv run pytest -q tests/test_semantic_objects.py`; `git diff --check`.
- 2026-05-05 19:48 EEST: Completed S2. Added ABI-aware `.tm` program artifact read/write paths, kept raw `TMTransitionProgram` IO metadata-blind, and updated artifact/CLI tests to read metadata from the file. Validation: `uv run pytest -q tests/test_semantic_objects.py tests/test_tm_file_input.py`; `git diff --check`.
- 2026-05-05 19:51 EEST: Completed S3. Fixed compiler endpoint fallback order, added source blank mismatch rejection, and made selected ABI validation reject grammar-version mismatches. Validation: `uv run pytest -q tests/test_semantic_objects.py tests/test_tm_file_input.py`; `git diff --check`.
- 2026-05-05 19:53 EEST: Completed S4. Added runtime artifact ABI compatibility checks, changed CLI `run` to preserve program-side `.tm` metadata, and covered compatible, incompatible, missing metadata, and CLI regression paths. Validation: `uv run pytest -q tests/test_semantic_objects.py tests/test_tm_file_input.py`; `git diff --check`.
- 2026-05-05 19:54 EEST: Completed S5. Added `TMTransitionProgram.transitions` as a read-only conceptual alias over `prog` and covered it in semantic object tests. Validation: `uv run pytest -q tests/test_semantic_objects.py`; `git diff --check`.
- 2026-05-05 19:58 EEST: Completed S6. Added `SourceArtifact`, safe `.mtm.source` read/write helpers, `.py` source artifact emission, and CLI `emit-source`. Validation: `uv run pytest -q tests/test_semantic_objects.py tests/test_tm_file_input.py`; `git diff --check`.
- 2026-05-05 20:00 EEST: Completed S8. Added raw-guest ABI inference and `build_raw_guest_encoding(...)` with `S` move support, plus a dispatch test documenting that non-left/non-right moves stay put. Validation: `uv run pytest -q tests/test_semantic_objects.py`; `git diff --check`.
- 2026-05-05 20:02 EEST: Tightened S8. Preserved existing raw `L`/`R` direction IDs when `S` is present and added unsupported raw move rejection coverage. Validation: `uv run pytest -q tests/test_semantic_objects.py`; `git diff --check`.
- 2026-05-05 20:04 EEST: Completed S9. Added `compile_raw_guest(...)`, raw sparse tape conversion with blank head preservation, and tests for compiling a trivial raw guest into a runnable UTM band. Validation: `uv run pytest -q tests/test_semantic_objects.py`; `git diff --check`.
- 2026-05-05 20:06 EEST: Completed S10. Added CLI `l1` / `l2` artifact workflows, including source/l1 artifact emission and raw-instance-based l2 generation. Validation: `uv run pytest -q tests/test_tm_file_input.py`; `uv run pytest -q`; `git diff --check`.

## Findings / Debt

- [ ] D1: `to_run_config(...)` compatibility alias remains.
  Impact: Keeps existing callers working, but the old name can preserve obsolete vocabulary.
  Recommendation: Delay removal until raw-guest compilation lands and external call sites have had one compatibility window.

- [ ] D2: No dedicated typecheck command is configured.
  Impact: Typed API renames rely on tests and import checks rather than a full static pass.
  Recommendation: Delay unless the tranche expands typed API surface significantly; otherwise keep recording exact pytest coverage per step.

## Completion Criteria

- All unchecked steps above are completed, validated, and committed with plan updates.
- `.tm` and `.utm.band` ABI metadata round-trips and runtime compatibility checks are covered by tests.
- Source artifacts round-trip without arbitrary Python execution.
- Raw `S` moves are supported on the raw-guest encoding path and covered by tests.
- `l1` and `l2` artifacts can be produced by the CLI.
- `l2` artifacts can be executed for bounded fuel without artifact, compatibility, or decode errors.
- Final validation includes `uv run pytest -q`, `git diff --check`, and representative CLI smoke coverage.
