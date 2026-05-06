# Debugger REPL Spec

This document defines the terminal debugger interface for MTM.

The debugger is a stateful in-process REPL. It does not persist debugger
sessions between shell commands. A session is created by loading a fixture,
building the universal program and source map, constructing a `RawTraceRunner`,
and then accepting commands against that runner until `quit`.

## Core Invariant

The raw TM trace is the executable truth.

```text
raw transition row
  -> lowering op
  -> lowering routine
  -> Meta-ASM instruction
  -> Meta-ASM block
  -> simulated source-TM step
```

Only the raw transition row is executed. The higher levels are debugger
boundaries derived from source-map metadata and runtime trace history.

Responsibilities:

- `RawTraceRunner` owns execution, snapshots, source lookup, and guarded
  boundary stepping.
- `TransitionSourceMap` owns static raw-row-to-source attribution.
- `DebuggerSession` owns user-facing status, view, where, and setting text.
- `DebuggerShell` parses REPL commands and prints session output.

`cmd.Cmd` methods must not duplicate debugger semantics. They are only the
terminal adapter.

## Entry

Fixture mode:

```bash
mtm dbg incrementer
mtm dbg --fixture incrementer
```

Both forms resolve through the same fixture setup path.

Artifact mode:

```bash
mtm dbg utm.tm input.utm.band
```

Artifact mode loads a persisted `.tm` host and `.utm.band` input, rebuilds the
matching lowering source map for that band's encoding, and starts the same
debugger shell. It can use `--max-raw N` to override the grouped-step guard.

## Startup

Startup prints a compact status, not a full view.

```text
mtm debugger: fixture incrementer
type `help` for commands

status: running raw_step=0 max_raw=100000 history=0/0
snapshot: state='START_STEP' head=-155 read='#CUR_STATE'
where: block=START_STEP instruction=setup routine=0:seek op=0
instruction: SEEK #CUR_STATE L
mtmdbg>
```

## Commands

Canonical commands:

```text
status
view
where

step raw
step routine
step instruction
step block
step source

back raw
back routine
back instruction
back block
back source

set max-raw N
help
quit
```

Shortcuts:

```text
st  -> status
v   -> view
w   -> where

s   -> step raw
sr  -> step routine
si  -> step instruction
sb  -> step block
ss  -> step source

b   -> back raw
br  -> back routine
bi  -> back instruction
bb  -> back block
bs  -> back source

h   -> help
?   -> help
q   -> quit
```

Do not add `n` or `next`. In this debugger, "next" is ambiguous between raw,
routine, instruction, block, and simulated source-TM boundaries.

Do not add `so`. `ss` is the consistent shortcut for `step source`.

## Boundary Vocabulary

Internal boundary names:

```python
Boundary = Literal["raw", "routine", "instruction", "block", "source"]
```

Action statuses:

```python
ActionStatus = Literal[
    "stepped",
    "rewound",
    "halted",
    "stuck",
    "max_raw",
    "unmapped",
    "at_start",
]
```

Runner statuses:

```python
RunStatus = Literal["running", "halted", "stuck"]
```

`max_raw` is not a runner status. It is only the result of a guarded step
command stopping before the requested boundary is reached.

Structured result:

```python
@dataclass(frozen=True)
class DebuggerActionResult:
    boundary: Boundary
    status: ActionStatus
    raw_steps: int
    snapshot: RawTraceSnapshot
    source: RawTransitionSource | None
```

`raw` stepping does not require a source map and should not return `unmapped`.
`back` commands do not return `stepped`; successful rewind returns `rewound`.
When no earlier snapshot or segment exists, `back` returns `at_start` and
leaves the current snapshot unchanged.

Grouped boundaries require source-map locations. Without a source map:

```text
step instruction -> status=unmapped
step raw         -> executes normally
```

## Step Semantics

Snapshots are complete logical configurations: raw step count, state, head,
and the full sparse tape mapping. If snapshots are later optimized into deltas,
the delta representation must preserve whether a tape cell was absent/default
blank or explicitly present with the blank symbol.

`RawTraceRunner` uses a history cursor:

- snapshots are stored in execution order
- the cursor points at the current snapshot
- `back` moves the cursor backward
- `step` from a non-final cursor truncates future snapshots before appending
  new snapshots

`step raw` after halt or stuck returns the current snapshot with `raw_steps=0`
and `status=halted` or `status=stuck`.

Grouped stepping after halt or stuck also returns the current snapshot with
`raw_steps=0` and `status=halted` or `status=stuck`.

All grouped forward stepping executes at least one raw transition before
testing whether the target boundary was reached.

This prevents a command from stopping immediately when the runner is already
positioned at the beginning of an instruction, routine, block, or source step.

For `routine`, `instruction`, and `block`, the boundary identity is computed
from `RawTransitionSource`:

```text
routine      -> routine_index
instruction  -> (block_label, instruction_index)
block        -> block_label
```

Forward grouped stepping stops when the identity changes, or when execution
halts, gets stuck, becomes unmapped, or reaches `max_raw`.

If the boundary is not reached before the guard, the result is:

```text
status=max_raw
```

not `status=stepped`.

## Source-Step Semantics

`source` means one simulated source-TM transition, not Python source code and
not one Meta-ASM instruction.

For the current UTM, a simulated source-TM step starts when the universal
interpreter enters the `START_STEP` block. The source-step entry label is a
runner setting:

```python
source_step_entry_label = "START_STEP"
```

It should be configurable for future universal-program shapes.

`step source`:

```text
execute at least one raw transition
continue until current mapped block becomes START_STEP
after having previously left START_STEP
or halt/stuck/max_raw/unmapped
```

This avoids stopping immediately at launch, where the runner is already inside
`START_STEP`.

`TransitionSourceMap` must not contain `source_step_index`. Source-step identity
is runtime trace state, because the same raw row can execute in many UTM cycles.

## Back Semantics

`back raw` restores the previous snapshot. It does not invert a transition. If
the cursor is already at the first snapshot, it returns `status=at_start` and
does not change the current snapshot.

Grouped back commands scan snapshot history and restore an earlier snapshot at
the requested boundary. Raw transitions are not generally invertible, so all
rewind behavior must use recorded snapshots.

All grouped back commands use segment-start semantics.

A boundary segment starts at history index `i` when:

```python
i == 0 or boundary_id(i) != boundary_id(i - 1)
```

For `routine`, `instruction`, and `block`, `back X`:

```text
1. finds the current segment start: greatest segment start b <= cur
2. finds the previous segment start: greatest segment start p < b
3. restores snapshot p
```

It must restore the start of the previous segment, not the last raw row inside
the previous segment.

Example:

```text
raw_step  instruction
10        A   <- instruction A segment starts here
11        A
12        B   <- instruction B segment starts here
13        B
14        B   <- current
```

`back instruction` restores raw step `10`, not raw step `11`.

For `source`, use source-step segment starts.

A source-step boundary exists at history index `i` when:

```python
loc[i] is not None
and loc[i].block_label == source_step_entry_label
and (
    i == 0
    or (
        loc[i - 1] is not None
        and loc[i - 1].block_label != source_step_entry_label
    )
)
```

Unmapped spans do not silently create source-step boundaries. In fixture-mode
UTM debugging, source locations should be mapped. In future raw/artifact modes,
grouped source stepping should return `unmapped` rather than infer boundaries
across unmapped history.

Given the current history index `cur`, `back source`:

1. Finds the current source-step start: greatest boundary `b <= cur`.
2. Finds the previous source-step start: greatest boundary `p < b`.
3. Restores snapshot `p`.

If no previous source-step start exists, `back source` returns
`status=at_start` and does not change the current snapshot.

Examples:

```text
raw_step  block
0         START_STEP   <- source step 0 starts here
1         START_STEP
2         START_STEP
3         FIND_HEAD
...
122       START_STEP   <- source step 1 starts here
123       START_STEP
124       START_STEP
125       FIND_HEAD
...
260       START_STEP   <- source step 2 starts here
```

If currently at raw step `250`, `back source` restores raw step `0`.

If currently at raw step `300`, `back source` restores raw step `122`.

It must not land in the middle of a `START_STEP` segment.

## Status

`status` is compact. It is not a synonym for `view`.

Shape:

```text
status: running raw_step=456 max_raw=100000 history=456/456
snapshot: state='CHECK_READ' head=-42 read='#ACTIVE_RULE'
where: block=CHECK_READ instruction=1 routine=18:compare_global_local op=3
instruction: COMPARE_GLOBAL_LOCAL #CUR_SYMBOL #READ 2
```

`history=A/B` means the current history cursor is at index `A`, and the latest
stored snapshot is at index `B`. After rewinding, `A` may be smaller than `B`.
If a new step is taken from a rewound cursor, snapshots after `A` are truncated
before the new step is appended.

Statuses:

```text
running
halted
stuck
```

`max_raw` is a step result, not a persistent runner status.

## Where

`where` prints only the current lowered source location.

Shape:

```text
where: block=CHECK_READ instruction=1 routine=18:compare_global_local op=3
row: state='...' read='...'
instruction: COMPARE_GLOBAL_LOCAL #CUR_SYMBOL #READ 2
```

If no source map location is available:

```text
where: <unmapped>
```

Use `where`, not `source`, in user-facing output. "Source" is overloaded in
this project.

Synthetic block-entry setup displays as `instruction=setup`, not `?`. Real
Meta-ASM instructions display their numeric instruction index.

## View

`view` is the heavier diagnostic command.

It includes:

- compact status
- raw snapshot
- raw tape window
- current raw transition row
- last raw transition row
- `where`
- decoded semantic registers and simulated tape, when available
- decode error when semantic decoding was requested but fails

Semantic decode must degrade cleanly:

```text
semantic: unavailable
```

or:

```text
semantic: <decode error: ...>
```

The debugger must not crash just because a mid-routine runtime tape is not
currently decodable as a coherent UTM band.

## Step Output

After `step ...` or `back ...`, print compact result text.

Shape:

```text
step instruction: status=stepped raw_steps=123
snapshot: raw_step=456 state='CHECK_READ' head=-42 read='#ACTIVE_RULE'
where: block=CHECK_READ instruction=1 routine=18:compare_global_local op=3
row: state='...' read='...' -> next='...' write='...' move=R
instruction: COMPARE_GLOBAL_LOCAL #CUR_SYMBOL #READ 2
```

For guard exhaustion:

```text
step instruction: status=max_raw raw_steps=100000
snapshot: raw_step=123456 state='...' head=...
where: ...
```

`stepped` means the requested boundary was reached.

`max_raw` means the debugger stopped protectively before reaching the boundary.

Back output uses `rewound`, not `stepped`:

```text
back instruction: status=rewound raw_steps=314
snapshot: raw_step=122 state='START_STEP' head=-155 read='#CUR_STATE'
where: block=START_STEP instruction=setup routine=0:seek op=0
instruction: SEEK #CUR_STATE L
```

At the beginning of history:

```text
back raw: status=at_start raw_steps=0
snapshot: raw_step=0 state='START_STEP' head=-155 read='#CUR_STATE'
where: block=START_STEP instruction=setup routine=0:seek op=0
instruction: SEEK #CUR_STATE L
```

## Settings

The first REPL supports exactly one setting:

```text
set max-raw N
```

Rules:

- `N` must be a positive integer.
- The default is `100000`.
- Do not add a generic settings system yet.

Invalid setting:

```text
unknown setting: foo
usage: set max-raw N
```

Invalid value:

```text
max-raw must be a positive integer
usage: set max-raw N
```

## Help

Help text:

```text
mtm debugger

Commands:
  status               Show compact runner status
  view                 Show raw + source + semantic trace view
  where                Show current lowered source location only

  step raw             Step one raw TM transition
  step routine         Step to next lowering routine
  step instruction     Step to next Meta-ASM instruction
  step block           Step to next Meta-ASM block
  step source          Step until one simulated source-TM transition completes

  back raw             Rewind one raw TM transition
  back routine         Rewind to previous lowering routine
  back instruction     Rewind to previous Meta-ASM instruction
  back block           Rewind to previous Meta-ASM block
  back source          Rewind to previous simulated source-TM transition start

  set max-raw N        Set grouped-step raw transition guard
  help                 Show this help
  quit                 Exit debugger

Shortcuts:
  st=status, v=view, w=where
  s=step raw, sr=step routine, si=step instruction, sb=step block, ss=step source
  b=back raw, br=back routine, bi=back instruction, bb=back block, bs=back source
  h/help/?=help, q=quit
```

## Invalid Commands

Unknown command:

```text
unknown command: foo
type `help` for commands
```

Invalid boundary:

```text
unknown boundary: foo
usage: step raw|routine|instruction|block|source
```

or:

```text
usage: back raw|routine|instruction|block|source
```

Missing boundary:

```text
usage: step raw|routine|instruction|block|source
```

or:

```text
usage: back raw|routine|instruction|block|source
```

Malformed setting:

```text
usage: set max-raw N
```

## Tests Required

Implementation must include tests for:

- `step raw` advances exactly one raw row.
- `step instruction` executes at least one raw row before boundary checking.
- `step instruction` returns `status=max_raw` when the guard is hit.
- `step source` from initial `START_STEP` executes nonzero raw rows.
- `back raw` restores the previous snapshot exactly.
- `back raw` at the initial snapshot returns `at_start` and leaves state
  unchanged.
- `back instruction` lands at the start of the previous instruction segment,
  not the last row inside it.
- `back block` lands at the start of the previous block segment, not the last
  row inside it.
- `back source` from source step 2 lands at the start of source step 1.
- `back source` from source step 1 lands at the start of source step 0.
- `back source` from source step 0 returns `at_start` and leaves state
  unchanged.
- stepping after rewinding truncates future history before appending new
  snapshots.
- `step raw` after halted/stuck returns `halted`/`stuck` with `raw_steps=0`.
- grouped step after halted/stuck returns `halted`/`stuck` with `raw_steps=0`.
- grouped stepping without a source map returns `unmapped`.
- raw stepping without a source map still works.
- `status` does not include tape windows or semantic dumps.
- `view` includes semantic decode when available.
- `view` includes `decode_error` instead of raising when decoding fails.
- aliases dispatch to the same session methods as canonical commands.
- `set max-raw` rejects non-integers and non-positive values.
- `step` with no argument prints usage.
- `back` with no argument prints usage.
- malformed `set` commands print usage.
