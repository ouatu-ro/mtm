# Plan: ABI Lattice Delimited Fields

## Goal

Make a wider generated UTM host run a valid narrower encoded band without
padding or reinterpreting guest fields, while preserving exact-ABI behavior.

## Scope

In scope:
- Carry guest-owned constants on the band: halt state, blank symbol, left move,
  and right move.
- Change compare/copy semantics to be width-bounded and delimiter-aware.
- Use `#BLANK_SYMBOL` when constructing fresh simulated tape cells.
- Replace strict runtime ABI equality with `band_abi <= host_abi` compatibility.
- Update MetaASM host semantics, lowered TM semantics, semantic object parsing,
  docs, and focused tests together.

Out of scope:
- Full malformed-band verification beyond the checks needed for valid generated
  artifacts.
- Arbitrary resizing, shifting, or rewriting of encoded fields.
- Optimizing the extra delimiter comparison away.
- Running a full real lowered L2 incrementer to completion as part of this
  change.

## Assumptions

- Within one valid band, same-kind fields use one guest width.
- Host widths are maximum payload bounds, not semantic field widths.
- Field comparison checks at most `width + 1` positions: payload plus
  terminator.
- A transition into the guest halt state still performs its write and move; the
  next `START_STEP` halts after comparing `#CUR_STATE` with `#HALT_STATE`.
- The implementation should prefer `#BLANK_SYMBOL` over mutating
  `#CUR_SYMBOL`, because `#CUR_SYMBOL` should continue to mean the current
  read symbol.

## Steps

- [x] S1: Update object model and band layout constants.
  Add `#HALT_STATE`, `#BLANK_SYMBOL`, `#LEFT_DIR`, and `#RIGHT_DIR` to the
  structural alphabet, register-band layout, semantic register objects,
  pretty/parsing helpers, and generated fixture expectations.
- [x] S2: Remove guest-width literals from the universal interpreter.
  Replace baked halt and direction literal checks with band-field comparisons.
  Add or expose `COMPARE_GLOBAL_GLOBAL` if needed by MetaASM and lowering.
- [ ] S3: Implement delimiter-aware compare and copy in the MetaASM host.
  Model width-bounded comparison/copy using terminators as the actual field or
  cell boundary, including cell-field copy cases with distinct terminators.
- [ ] S4: Lower delimiter-aware compare and copy to raw TM transitions.
  Keep exact-ABI behavior valid, but allow early terminator success for smaller
  bands under wider hosts. Use `#BLANK_SYMBOL` for tape expansion.
- [ ] S5: Relax runtime compatibility checks.
  Accept `band_abi <= host_abi`, reject `band_abi > host_abi`, and keep raw TM
  execution independent of ABI metadata.
- [ ] S6: Add focused tests and regenerate fixtures only where intentional.
  Cover wider-host/smaller-band incrementer, halt-after-final-write/move,
  blank-cell expansion width, exact-ABI regression, and metadata rejection when
  the band is wider than the host.
- [ ] S7: Run validation and update this plan.
  Record exact commands, results, remaining debt, and commit checkpoints once
  implementation begins.

## Validation

- Typecheck:
  - Not identified yet.
- Lint:
  - Not identified yet.
- Tests:
  - `pytest tests/test_semantic_objects.py`
  - `pytest tests/test_lowering.py`
  - `pytest tests/test_meta_asm_host.py` if present, otherwise the nearest
    MetaASM host test module.
  - Focused CLI/runner test that proves a wider UTM host executes a narrower
    incrementer band to `1100`.
- Final checks:
  - `git status --short`
  - `rg -n "HALT_BITS|L_BITS|R_BITS|strict ABI|all-zero blank" mtm tests docs Spec.md object_model.md`

## Progress Log

- 2026-05-06 07:25 EEST: Plan created. `Spec.md` updated first by request;
  no commit created because the user explicitly asked not to commit yet.
- 2026-05-06 07:35 EEST: S1 completed. Added band-owned constants to the
  register layout, semantic register decode/re-encode, pretty parsing, object
  model docs, and focused semantic-object tests. Validation:
  `uv run python -m pytest tests/test_semantic_objects.py tests/test_tm_file_input.py`.
- 2026-05-06 07:43 EEST: S2 completed. Added `COMPARE_GLOBAL_GLOBAL`, switched
  the universal program to band-field halt and direction comparisons, updated
  debugger/trace expectations, and kept compare semantics exact-width for now.
  Validation: `uv run python -m pytest tests/test_meta_asm.py tests/test_semantic_objects.py::test_universal_dispatch_treats_non_left_non_right_direction_as_stay tests/test_lowering.py::test_lowered_start_step_matches_host_block tests/test_lowering.py::test_compare_global_global_matches_host_block tests/test_debugger_session.py::test_session_status_query_and_render_include_cursor_latest_and_max_raw tests/test_debugger_session.py::test_session_where_renders_setup_for_entry_location tests/test_debugger_presenter.py::test_presenter_status_doc_exposes_block_structure tests/test_raw_trace.py::test_format_trace_view_renders_semantic_summary_for_decoded_band tests/test_tm_file_input.py::test_cli_trace_emits_raw_instruction_and_block_levels`.

## Findings / Debt

- [x] D1: Direction constants have the same ABI-width issue as halt state.
  Impact: A wider host comparing `#MOVE_DIR` against baked host-width `L` or
  `R` literals would still reject a valid narrower band.
  Resolved: S1 added `#LEFT_DIR` and `#RIGHT_DIR`; S2 switched dispatch to
  compare `#MOVE_DIR` against those band fields.
- [ ] D2: Cell-field copies use different terminators.
  Impact: `#END_CELL` and `#END_FIELD` are not interchangeable, so head-symbol
  copies must stop on the source terminator while preserving the destination's
  existing terminator shape.
  Recommendation: Do now in S3/S4, but keep it narrow and avoid general
  field-resizing machinery.
- [x] D3: `OBJECT_MODEL.md` still needs the same terminology update as
  `Spec.md`.
  Resolved: S1 updated the tracked object-model document with the band-owned
  constant register fields.

## Completion Criteria

- A host UTM with wider state/symbol/direction widths can execute a valid
  narrower incrementer band and produce `1100`.
- Exact-ABI incrementer behavior remains unchanged except for the intentional
  extra terminator comparison.
- A transition into halt writes, moves, and updates `#CUR_STATE` before the next
  `START_STEP` halts.
- Fresh blank cells on either side use the band's `#BLANK_SYMBOL` width.
- Docs and tests describe the same ABI compatibility rule.
