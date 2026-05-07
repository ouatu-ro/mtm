# Plan: ABI Lattice Delimited Fields

## Goal

Make a wider generated UTM host run a valid narrower encoded tape without
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
- [x] S3: Implement delimiter-aware compare and copy in the MetaASM host.
  Model width-bounded comparison/copy using terminators as the actual field or
  cell boundary, including cell-field copy cases with distinct terminators.
- [x] S4: Lower delimiter-aware compare and copy to raw TM transitions.
  Keep exact-ABI behavior valid, but allow early terminator success for smaller
  bands under wider hosts. Use `#BLANK_SYMBOL` for tape expansion.
- [x] S5: Relax runtime compatibility checks.
  Accept `band_abi <= host_abi`, reject `band_abi > host_abi`, and keep raw TM
  execution independent of ABI metadata.
- [x] S6: Add focused tests and regenerate fixtures only where intentional.
  Cover wider-host/smaller-band incrementer, halt-after-final-write/move,
  blank-cell expansion width, exact-ABI regression, and metadata rejection when
  the band is wider than the host.
- [x] S7: Run validation and update this plan.
  Record exact commands, results, remaining debt, and commit checkpoints once
  implementation begins.

## Validation

- Typecheck:
  - `uv run python -m py_compile mtm/source_encoding.py mtm/meta_asm_host.py mtm/lowering/instruction_lowering.py tests/test_lowering.py tests/test_semantic_objects.py`
- Lint:
  - Not identified yet.
- Tests:
  - `uv run python -m pytest tests/test_semantic_objects.py tests/test_tm_file_input.py tests/test_lowering.py tests/test_meta_asm.py`
  - `uv run python -m pytest`
- Final checks:
  - `git status --short`
  - `rg -n "HALT_BITS|L_BITS|R_BITS|strict ABI|all-zero blank" mtm tests docs Spec.md OBJECT_MODEL.md object_model.md`

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
  Validation: `uv run python -m pytest tests/test_meta_asm.py tests/test_semantic_objects.py::test_universal_dispatch_treats_non_left_non_right_direction_as_stay tests/test_lowering.py::test_lowered_start_step_matches_host_block tests/test_lowering.py::test_compare_global_global_matches_host_block tests/test_debugger_session.py::test_session_status_query_and_render_include_cursor_latest_and_max_raw tests/test_debugger_session.py::test_session_where_renders_setup_for_entry_location tests/test_debugger_presenter.py::test_presenter_status_doc_exposes_block_structure tests/test_raw_trace.py::test_format_trace_view_renders_semantic_summary_for_decoded_utm_view tests/test_tm_file_input.py::test_cli_trace_emits_raw_instruction_and_block_levels`.
- 2026-05-06 07:49 EEST: S3 completed. MetaASM host compare/copy now uses
  delimiter-aware, width-bounded field and cell regions while preserving
  destination terminator shape. Validation: `uv run python -m py_compile
  mtm/meta_asm_host.py tests/test_lowering.py`; `uv run python -m pytest
  tests/test_lowering.py -k 'compare_global_global_matches_host_block or
  meta_asm_host_compare_global_global_stops_at_matching_early_terminators or
  meta_asm_host_compare_global_local_fails_when_one_field_ends_early or
  meta_asm_host_copy_global_global_preserves_early_end_field_shape or
  meta_asm_host_copy_head_symbol_to_preserves_end_field_shape or
  meta_asm_host_copy_global_to_head_symbol_preserves_end_cell_shape or
  meta_asm_host_copy_local_global_raises_on_delimiter_mismatch or
  meta_asm_host_finds_and_reads_left_band_head_cell or
  meta_asm_host_moves_between_right_and_left_simulated_tape'`.
- 2026-05-06 07:56 EEST: S4 completed. Raw TM lowering now mirrors the host
  delimiter-aware compare/copy behavior for global/global, global/local,
  local/global, and head-symbol copy paths. Validation: `uv run python -m
  py_compile mtm/lowering/instruction_lowering.py tests/test_lowering.py`;
  `uv run python -m pytest tests/test_lowering.py -k
  'compare_global_global_matches_host_block or
  lowered_compare_global_global_stops_at_matching_early_terminators or
  meta_asm_host_compare_global_global_stops_at_matching_early_terminators or
  lowered_compare_global_local_fails_when_one_field_ends_early or
  meta_asm_host_compare_global_local_fails_when_one_field_ends_early or
  lowered_copy_global_global_preserves_early_end_field_shape or
  meta_asm_host_copy_global_global_preserves_early_end_field_shape or
  lowered_copy_head_symbol_to_preserves_end_field_shape or
  meta_asm_host_copy_head_symbol_to_preserves_end_field_shape or
  lowered_copy_global_to_head_symbol_preserves_end_cell_shape or
  meta_asm_host_copy_global_to_head_symbol_preserves_end_cell_shape or
  lowered_copy_local_global_stucks_on_delimiter_mismatch or
  meta_asm_host_copy_local_global_raises_on_delimiter_mismatch or
  lowered_start_step_matches_host_block'`.
- 2026-05-06 08:08 EEST: S4 follow-up completed. Fixed `DISPATCH_MOVE` block
  setup to seek right to `#MOVE_DIR` after `MATCHED_RULE`, since the old
  post-copy halt comparison no longer positions the head to the right of the
  move register. Validation: `uv run python -m pytest
  tests/test_semantic_objects.py::test_utm_program_artifact_round_trip_and_run
  tests/test_semantic_objects.py::test_universal_interpreter_for_encoded_matches_direct_lowering
  tests/test_semantic_objects.py::test_wider_abi_incrementer_runs_end_to_end`;
  `uv run python -m pytest tests/test_lowering.py -k
  'lowered_start_step_matches_host_block or compare_global_global_matches_host_block
  or lowered_compare_global_global_stops_at_matching_early_terminators or
  lowered_copy_global_to_head_symbol_preserves_end_cell_shape'`.
- 2026-05-06 08:09 EEST: S5 completed. Runtime ABI compatibility now accepts
  host widths greater than or equal to band widths while still rejecting
  narrower hosts and grammar mismatches. Validation: `uv run python -m pytest
  tests/test_semantic_objects.py -k
  'runtime_abi_compatibility_allows_wider_host_and_rejects_narrower_host or
  utm_program_artifact_run_allows_missing_program_abi_metadata or
  utm_program_artifact_run_rejects_incompatible_abi_metadata or
  utm_program_artifact_run_allows_wider_program_abi_metadata'`; `uv run
  python -m pytest tests/test_tm_file_input.py -k
  'cli_run_preserves_program_side_abi_metadata or
  cli_run_rejects_program_abi_narrower_than_band'`.
- 2026-05-06 08:23 EEST: S6 completed. Fresh simulated tape expansion now
  copies the band-owned `#BLANK_SYMBOL` payload in both the MetaASM host and
  lowered raw TM, with focused wider-host/narrow-blank tests and right-side
  halt write/move coverage. Existing movement tests now use fuel that matches
  the more expensive runtime blank-copy path. Validation: `uv run python -m
  py_compile mtm/source_encoding.py mtm/meta_asm_host.py
  mtm/lowering/instruction_lowering.py tests/test_lowering.py
  tests/test_semantic_objects.py`; `uv run python -m pytest
  tests/test_lowering.py -k 'move_sim_head_right_expands_with_band_blank_symbol_payload
  or move_sim_head_left_expands_with_band_blank_symbol_payload or
  lowered_start_step_matches_host_block or compare_global_global_matches_host_block
  or lowered_compare_global_global_stops_at_matching_early_terminators'`; `uv
  run python -m pytest tests/test_semantic_objects.py -k
  'wider_host_runs_narrow_incrementer_band_end_to_end or
  wider_abi_incrementer_runs_end_to_end or halt_transition_moves_after_writing_on_left_tape
  or halt_transition_moves_after_writing_on_right_tape'`; `uv run python -m
  pytest tests/test_lowering.py -k 'move_sim_head'`.
- 2026-05-06 08:35 EEST: S7 completed. Broad validation exposed stale fuel
  limits for more expensive delimiter-copy paths and a source-trace assertion
  that still expected one partial row; both were updated to match the new
  completed-step behavior. Validation: `uv run python -m pytest
  tests/test_semantic_objects.py::test_one_step_right_constructs_blank_right_cell_end_to_end
  tests/test_tm_file_input.py::test_cli_trace_emits_raw_instruction_and_block_levels
  tests/test_lowering.py::test_first_lowered_fragments_smoke`; `uv run python
  -m pytest tests/test_semantic_objects.py tests/test_tm_file_input.py
  tests/test_lowering.py tests/test_meta_asm.py` (`116 passed`); `uv run
  python -m pytest` (`170 passed`); `git status --short`; `rg -n
  "HALT_BITS|L_BITS|R_BITS|strict ABI|all-zero blank" mtm tests docs Spec.md
  OBJECT_MODEL.md object_model.md` (no matches).

## Findings / Debt

- [x] D1: Direction constants have the same ABI-width issue as halt state.
  Impact: A wider host comparing `#MOVE_DIR` against baked host-width `L` or
  `R` literals would still reject a valid narrower band.
  Resolved: S1 added `#LEFT_DIR` and `#RIGHT_DIR`; S2 switched dispatch to
  compare `#MOVE_DIR` against those band fields.
- [x] D2: Cell-field copies use different terminators.
  Impact: `#END_CELL` and `#END_FIELD` are not interchangeable, so head-symbol
  copies must stop on the source terminator while preserving the destination's
  existing terminator shape.
  Resolved: S3 and S4 model and lower cell-field copies by stopping on the
  source terminator while preserving the destination terminator shape.
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
