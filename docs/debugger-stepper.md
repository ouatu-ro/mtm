# Debugger Stepper Layers

The debugger surface is easiest to teach if you treat it as four stacked
layers:

1. raw TM stepping
2. source-map lookup
3. grouped stepping
4. semantic band decode

Each layer adds context without changing the underlying execution model.

## 1. Raw TM stepping

`mtm.debugger.RawTraceRunner` executes one row of a
`TMTransitionProgram` at a time and stores full immutable snapshots.

- `step()` advances one concrete `(state, read_symbol)` row
- `back()` restores the previous snapshot
- `run(max_steps)` stops at `halted`, `stuck`, or `fuel_exhausted`

At this layer the debugger is only concerned with the ordinary raw machine:
tape, head, state, and the concrete row that executed.

## 2. Source-map lookup

`mtm.lowering.lower_program_with_source_map(...)` returns both the lowered raw
program and a `TransitionSourceMap`.

Passing that map into `RawTraceRunner(..., source_map=...)` lets the runner
attach `RawTransitionSource` metadata to:

- the next raw row via `current_transition_source`
- the last executed raw row via `last_transition_source`

This is the bridge from "what raw row am I on?" to "which lowered block,
instruction, routine, and op produced this row?"

## 3. Grouped stepping

Once source metadata is available, the runner can move by larger teaching
units instead of single raw rows:

- `step_to_next_routine()` / `back_to_previous_routine()`
- `step_to_next_instruction()` / `back_to_previous_instruction()`
- `step_to_next_block()` / `back_to_previous_block()`
- `step_to_next_source_step()` / `back_to_previous_source_step()`

These still execute and rewind raw rows internally. The difference is only the
boundary used to stop.

`source step` is the UTM-cycle boundary keyed off the `START_STEP` block by
default. Pass `source_step_block_label=...` to `RawTraceRunner` if a different
universal-program shape uses a different cycle-entry label. This mode is useful
when teaching the universal machine as a repeated fetch/decode/apply loop over
an encoded source machine.

## 4. Semantic band decode

`RawTraceRunner.current_view(encoding=...)` adds a decoded semantic view when
the current runtime tape is a coherent encoded UTM band.

`RawTraceView` combines:

- the current raw snapshot
- the next raw row
- source metadata for the next or last row
- an optional `DecodedBandView`

This is the teaching-friendly "show me both the raw interpreter state and the
simulated source-machine state" layer.

## Recommended teaching sequence

For demos and UI wiring, the simplest progression is:

1. start with `step()` and `format_trace_view(...)`
2. add `source_map` from `lower_program_with_source_map(...)`
3. switch controls to grouped stepping when raw rows become too fine-grained
4. pass `encoding` to `current_view(...)` when you want to show decoded
   registers and simulated tape

That order keeps the mental model stable: every richer view is still grounded
in the same reversible raw trace.
