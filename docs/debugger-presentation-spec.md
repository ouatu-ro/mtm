# Debugger Presentation Model Spec

This document defines the target presentation and read-model architecture for
the MTM debugger.

The goal is to stop treating the terminal transcript as the source of truth.
The debugger should instead produce:

- a query-shaped read model over trace facts
- a shared presentation model over query results

That stack should drive:

- plain REPL text
- ANSI-colored REPL text
- command help
- future TUI surfaces
- future Web UI surfaces

This spec does not change debugger execution semantics. It changes the
representation boundary between debugger state and debugger output, and it
defines the first read-model architecture that sits between them.

## Problem

The current debugger surface is too string-first.

Today, session summaries, help metadata, plain text formatting, ANSI styling,
and derived debugger views are too tightly coupled. That shows up in several
ways:

- session code depends on rendering helpers
- derived debugger views are assembled imperatively in session methods
- help text duplicates output concepts in prose form
- ANSI styling post-processes rendered text
- presentation strings are baked into intermediate objects

This makes the REPL work, but it is a poor source model for any non-terminal
surface.

## Core Rule

The shared model must describe debugger concepts, not terminal layout.

The CLI is one rendering of that model. It is not the model itself.

The debugger read API should also be query-shaped, not string-shaped.

## Scope

This spec covers:

- trace facts and query boundaries
- debugger presentation objects
- presenter input/output shape
- presenter responsibilities
- renderer responsibilities
- help metadata ownership
- migration order

This spec does not cover:

- new debugger commands
- breakpoint semantics
- relational trace queries
- artifact-mode debugger initialization

## Existing Semantic Layers

The debugger already has a useful semantic stack:

1. raw TM stepping
2. source-map lookup
3. grouped stepping
4. semantic band decode
5. session/shell presentation

See [debugger-stepper.md](/Users/bg/repos/mtm/docs/debugger-stepper.md).

This spec refines only layer 5.

## Target Split

The debugger should be split into five distinct layers:

1. imperative execution/history
2. trace fact store
3. query layer
4. presentation model
5. renderers and shell/CLI orchestration

Responsibilities:

- `RawTraceRunner` owns execution, history, source lookup, and grouped step
  semantics.
- `TraceFacts` owns the derived relational index over execution history.
- `DebuggerQueries` owns debugger read views over trace facts.
- `DebuggerSession` owns command semantics and mutation only.
- `DebuggerPresenter` owns conversion from query results into shared
  presentation objects.
- renderers own terminal text, ANSI color, and future UI-specific output.
- `DebuggerShell` owns parsing and wiring only.

`DebuggerSession` must not be a text API long-term, and it should not be the
main place where debugger read views are assembled.

## Imperative Core

These parts stay imperative Python:

- raw TM execution
- history cursor movement
- truncating future history after stepping from the past
- guarded `max_raw` stepping loops
- tape window extraction
- semantic decode, at least initially
- shell I/O

This is not a proposal to reimplement TM stepping inside a relational engine.

## Trace Facts

The first read-model backend should be a custom Python fact/query layer behind
clean interfaces.

Do not adopt a Datalog engine as part of the first refactor.

The implementation target is:

- in-memory Python fact storage
- query helpers over named relations
- swappable backend boundary for a future Datalog/Cozo implementation if
  debugger needs expand

Named relations are preferred to EAV for the debugger core.

Examples:

```text
snapshot(step, state, head, read)
event(step, state, read, write, move, next_state)
source(step, block, instr, routine_index, routine_name, op)
instruction(step, opcode, args, explanation)
boundary(step, kind, key)
decoded(step, source_state, source_head, source_symbol)
register(step, name, value)
semantic_tape_cell(step, addr, symbol)
decode_error(step, message)
```

The exact schema can evolve, but the read model should be relation-shaped from
the start.

## Query Layer

Most debugger read views are projections over the trace, not deep domain
entities.

Examples:

- current status
- current source location
- next row
- last row
- next boundary
- previous boundary
- semantic view
- command help joins
- trace filtering and search

The query layer should present typed query APIs even if the underlying fact
store is generic.

Suggested surface:

```python
class DebuggerQueries:
    def status(self) -> StatusRow: ...
    def where(self) -> WhereRow: ...
    def view(self) -> ViewRows: ...
    def next_boundary(self, kind: str, after: int) -> int | None: ...
    def previous_boundary(self, kind: str, before: int) -> int | None: ...
    def command_help(self, topic: str | None) -> HelpRows: ...
```

This keeps the rest of the debugger from depending on ad hoc dictionaries or
query-language strings.

## Query Results

The first presenter input does not need to be fully generic rows.

Typed query result objects are a good compromise.

Examples:

- `StatusRow`
- `WhereRow`
- `ActionRow`
- `ViewRow`
- `HelpRow`

These are not deep entities. They are typed projections over the fact store.

## Existing Summaries

The current summary dataclasses may remain temporarily as compatibility glue,
but they should stop being the long-term center of the design.

These may include:

- `DebuggerRunnerSummary`
- `DebuggerLocationSummary`
- `DebuggerTransitionSummary`
- `DebuggerSemanticSummary`
- `DebuggerActionSummary`
- `DebuggerViewSummary`

They should be moved out of the rendering module if retained.

Long-term, query results should replace most summary construction inside
`DebuggerSession`.

Important rule:

Do not pre-render UI strings into summaries where avoidable.

Prefer structured values such as:

- raw move as a direction enum or integer, not `"L"`/`"R"`/`"S"`
- routine index and routine name separately, not only `"18:compare_global_local"`
- tape windows as structured cells, not only a final formatted string

The query layer, presenter, or renderer may choose the final display form,
depending on the field.

## Presentation Model

Start with a shared block-oriented AST.

Do not make `Line` the primary source model.

`Line` may exist later as a renderer-side lowering target, but the shared
model should remain UI-neutral enough for terminal, TUI, and Web UI output.

Minimal shape:

```python
@dataclass(frozen=True)
class Field:
    key: str
    value: object
    role: str | None = None
    doc: str | None = None


@dataclass(frozen=True)
class Block:
    kind: str
    title: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class RecordBlock(Block):
    fields: tuple[Field, ...] = ()


@dataclass(frozen=True)
class InstructionBlock(Block):
    opcode: str = ""
    args: tuple[object, ...] = ()
    explanation: str | None = None


@dataclass(frozen=True)
class TransitionBlock(Block):
    state: str | None = None
    read_symbol: str | None = None
    write_symbol: str | None = None
    move: object | None = None
    next_state: str | None = None
    present: bool = True


@dataclass(frozen=True)
class TapeBlock(Block):
    cells: tuple[tuple[int, str], ...] = ()
    head: int | None = None
    blank_symbol: str | None = None


@dataclass(frozen=True)
class MessageBlock(Block):
    text: str = ""


@dataclass(frozen=True)
class TableBlock(Block):
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class Document:
    kind: str
    title: str | None = None
    status: str | None = None
    blocks: tuple[Block, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
```

This is intentionally small.

It should be expressive enough for current debugger output without committing
the rest of the system to terminal lines as the main abstraction.

## Semantic Roles

Roles should remain semantic and boring.

Suggested starter roles:

```python
ROLE_STATUS = "status"
ROLE_COUNTER = "counter"
ROLE_RAW = "raw"
ROLE_SOURCE = "source"
ROLE_INSTRUCTION = "instruction"
ROLE_OPCODE = "opcode"
ROLE_ARG = "arg"
ROLE_TRANSITION = "transition"
ROLE_TAPE = "tape"
ROLE_SEMANTIC = "semantic"
ROLE_REGISTER = "register"
ROLE_HELP = "help"
ROLE_WARNING = "warning"
ROLE_ERROR = "error"
```

Do not overfit roles to one renderer.

If the text and ANSI renderers do not need more specificity, do not add it.

## Canonical Blocks

The current REPL vocabulary should map cleanly to canonical block types:

- `RAW` -> `RecordBlock`
- `SOURCE` -> `RecordBlock`
- `INSTRUCTION` -> `InstructionBlock`
- `NEXT ROW` -> `TransitionBlock`
- `LAST ROW` -> `TransitionBlock`
- `RAW TAPE` -> `TapeBlock`
- `SEMANTIC` -> `RecordBlock` or `MessageBlock`
- `SEM TAPE` -> `TapeBlock`
- `REGS` -> `RecordBlock`
- `HELP TABLE` -> `TableBlock`

Example for one step:

```python
Document(
    kind="action",
    status="stepped",
    metadata={"verb": "step", "boundary": "raw", "raw_delta": 1},
    blocks=(
        RecordBlock(
            kind="raw",
            title="RAW",
            fields=(
                Field("raw", 1, role="counter"),
                Field("head", -155, role="raw"),
                Field("read", "#CUR_STATE", role="raw"),
                Field("state", "program_START_STEP_body_0", role="raw"),
            ),
        ),
        RecordBlock(
            kind="source",
            title="SOURCE",
            fields=(
                Field("block", "START_STEP", role="source"),
                Field("instr", 0, role="source"),
                Field("routine", ("compare_global_literal", 1), role="source"),
                Field("op", 0, role="source"),
            ),
        ),
        InstructionBlock(
            kind="instruction",
            title="INSTRUCTION",
            opcode="COMPARE_GLOBAL_LITERAL",
            args=("#CUR_STATE", "01"),
            explanation="Compare register #CUR_STATE against literal bits 01.",
        ),
        TransitionBlock(
            kind="next_row",
            title="NEXT ROW",
            state="program_START_STEP_body_0",
            read_symbol="#CUR_STATE",
            write_symbol="#CUR_STATE",
            move="L",
            next_state="program_START_STEP_body_0",
        ),
    ),
)
```

The CLI may render this as aligned lines, but the document itself is not a
line transcript.

## Presenter

The presenter is the boundary between query results and UI objects.

Suggested entry points:

```python
status_doc(status_row) -> Document
where_doc(where_row) -> Document
action_doc(action_row) -> Document
view_doc(view_row) -> Document
help_doc(topic: str | None) -> Document
```

The presenter may know debugger concepts such as:

- block/instruction/routine/op
- raw row semantics
- semantic decode availability
- instruction explanation text

The renderer must not know debugger semantics beyond what is present in the
document it receives.

## Renderers

The first renderers should be:

- `PlainTextRenderer`
- `AnsiRenderer`

Both render the same `Document`.

Do not style plain text after rendering with regex over terminal lines.

Not this:

```python
plain = PlainTextRenderer().render(doc)
styled = regex_colorize(plain)
```

But this:

```python
plain = PlainTextRenderer().render(doc)
ansi = AnsiRenderer().render(doc)
```

The text renderer may internally lower blocks to lines, but that lowering is a
renderer implementation detail, not the shared presentation model.

## Help Metadata

Help must move out of the renderer.

Recommended split:

- `CommandSpec`
- `FieldSpec`
- `OutputSpec`

Example:

```python
CommandSpec(
    name="step raw",
    aliases=("s",),
    usage="step raw [N]",
    summary="Advance by exactly one raw TM transition.",
    output="action",
)
```

`OutputSpec("action")` may describe the shared blocks:

- `RAW`
- `SOURCE`
- `INSTRUCTION`
- `NEXT ROW`

This avoids repeating the same output legend in many hard-coded help strings.

## File Layout

Target file split:

```text
mtm/debugger/facts.py
mtm/debugger/queries.py
mtm/debugger/summaries.py          # transitional, may shrink over time
mtm/debugger/presentation.py
mtm/debugger/presenter.py
mtm/debugger/render_text.py
mtm/debugger/render_ansi.py
mtm/debugger/help.py
mtm/debugger/session.py
mtm/debugger/shell.py
```

The current `render.py` should eventually disappear.

It currently mixes too many concepts:

- summary dataclasses
- fact/query concerns by implication
- plain text formatting
- ANSI styling
- help metadata
- instruction explanation helpers

## Migration Strategy

Recommended order:

1. Move help metadata out of `render.py` into `help.py`.
2. Move summary dataclasses out of `render.py` into `summaries.py`.
3. Add `facts.py` with a custom Python fact store over trace history.
4. Add `queries.py` with typed query APIs for `status`, `where`, `view`, and
   boundary lookup.
5. Make `DebuggerSession` command/mutation-oriented; keep `*_text()` as
   temporary wrappers.
6. Add `presentation.py` with the shared AST.
7. Add `presenter.py` and port `status` and `where`.
8. Add `render_text.py` and preserve byte-identical text output.
9. Port `step/back`, then `view`.
10. Add `render_ansi.py` from `Document`.
11. Delete regex-based ANSI post-processing.
12. Delete or collapse the old `render.py`.
13. Add machine-readable export only after the presentation model is stable.

## Deferred Work

These are explicitly deferred:

- JSON export contract stabilization
- Web UI schema design
- TUI layout design
- per-token hover docs or deeply nested instruction spans
- a Datalog-backed query engine such as Cozo
- fully relational tape reconstruction with aggregates
- EAV/provenance/annotation fact identity

The first implementation should prove the query shapes in plain Python before
introducing a database dependency.

If the debugger later needs persistent trace sessions, richer historical
queries, or more powerful analytics, the `facts.py` / `queries.py` boundary
should make a Cozo-style backend possible without changing presenter or
renderer contracts.

## Success Criteria

The refactor is successful when:

1. no file outside renderers formats debugger transcript lines directly
2. no renderer imports `RawTraceRunner`, `RawTransitionSource`, or Meta-ASM
   instruction classes
3. `DebuggerSession` no longer assembles debugger read views by hand
4. debugger read APIs are query-shaped
5. help and runtime output use the same semantic vocabulary
6. ANSI styling is derived from presentation roles, not regex over final text
7. a future TUI or Web UI can consume the shared document model without
   reparsing terminal strings

One strong negative check:

> No file outside renderers calls `f"{label:<12}"`, aligns transcript columns,
> injects ANSI escape codes, or constructs debugger output lines directly.

## Relationship To Current REPL Spec

The current REPL behavior remains defined by
[debugger-repl-spec.md](/Users/bg/repos/mtm/docs/debugger-repl-spec.md).

This document defines the architectural shape that should produce that REPL.

In short:

- `debugger-repl-spec.md` defines what the debugger says
- this document defines how debugger read and presentation layers should be
  structured
