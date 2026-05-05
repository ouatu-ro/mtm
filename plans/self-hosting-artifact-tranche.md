# Self-Hosting Artifact Tranche

## Goal

Make the artifact contract honest and unlock the first recursive self-hosting
workflow without blocking on an ABI-only universal host redesign.

This tranche focuses on:

- `.tm` metadata and compatibility
- compiler/runtime correctness gaps
- source artifact persistence
- raw guest compilation
- `l1` / `l2` artifact workflows

It does **not** try to make `UniversalInterpreter` ABI-only. That remains a
later cleanup because it is not required for `l2`.

## Target Outcomes

By the end of this tranche, the project should support:

- `.tm` artifacts that optionally persist `target_abi` / `minimal_abi`
- compatibility checks between `.tm` and `.utm.band` when both carry ABI data
- a serializable source artifact format
- a `RawTMInstance` object
- a raw-guest compiler path
- explicit `l1` / `l2` artifact production in the CLI

## Ordered Tasks

### 0. Add shared ABI literal and compatibility helpers

Factor ABI serialization and comparison into shared helpers before changing
artifact readers and writers.

Deliverables:

- shared helpers such as:
  - `abi_to_literal(abi: TMAbi) -> dict[str, object]`
  - `abi_from_literal(data: dict[str, object]) -> TMAbi`
  - `abi_compatible(a: TMAbi, b: TMAbi) -> bool`
  - `assert_abi_compatible(a: TMAbi, b: TMAbi) -> None`
- `.utm.band` and `.tm` artifact code use the same ABI literal path
- `.tm` ABI parsing does not depend on an `Encoding` fallback

Checkpoint:

- ABI literal round-trip test
- compatibility helper tests cover matching and mismatched ABIs

### 1. Make `.tm` metadata honest and usable

Persist optional ABI metadata in `.tm` while keeping reads backward-compatible.

Deliverables:

- `.tm` writer emits:
  - `target_abi` when known
  - `minimal_abi` when known
- `.tm` reader accepts both:
  - new `.tm` files with ABI metadata
  - old `.tm` files without it
- `UTMProgramArtifact.read(...)` yields:
  - `target_abi=None`
  - `minimal_abi=None`
  when the file did not persist them

Design choice for this tranche:

- keep `read_tm(path) -> TMTransitionProgram`
- add or tighten `UTMProgramArtifact.read(path) -> UTMProgramArtifact`
- factor shared low-level parsing so `.tm` files are not parsed twice unnecessarily
- keep `TMTransitionProgram.write(...)` as the raw-only writer
- make `UTMProgramArtifact.write(...)` the ABI-aware writer

Checkpoint:

- old fixture/tests still read existing `.tm` artifacts
- new tests cover read/write round-trip with and without ABI metadata

### 2. Fix compiler correctness gaps

Bring code into line with the current object/spec contract.

Deliverables:

- `Compiler` resolves endpoints in this order:
  1. `TMInstance.initial_state` / `halt_state`
  2. `TMProgram.initial_state` / `halt_state`
  3. `Compiler.initial_state` / `halt_state`
- instance values override program values without error when both are present
- compilation rejects `TMProgram.blank != TMBand.blank`
- ABI validation checks:
  - `state_width`
  - `symbol_width`
  - `dir_width`
  - `grammar_version`

Checkpoint:

- targeted compiler tests cover all three endpoint fallback sources
- tests cover blank mismatch failure
- tests cover grammar-version mismatch failure

### 3. Add artifact compatibility checks at run time

Make ABI metadata operational without making it an execution dependency.

Deliverables:

- running `.tm` against `.utm.band` checks compatibility only when both carry
  `target_abi`
- incompatibility rejects mismatched:
  - `grammar_version`
  - `state_width`
  - `symbol_width`
  - `dir_width`
- absence of `.tm` ABI metadata still allows execution
- `UTMProgramArtifact.run(...)` owns the check
- CLI `run` path preserves program-side ABI metadata instead of copying ABI
  from the band onto the program artifact

Checkpoint:

- tests cover:
  - both sides present and compatible
  - both sides present and incompatible
  - `.tm` without ABI metadata
- CLI `run` uses `UTMProgramArtifact.read(...)` or equivalent preserved ABI path

### 4. Add `TMTransitionProgram.transitions`

Small API/doc alignment cleanup.

Deliverables:

- read-only `transitions` alias over `prog`

Checkpoint:

- no existing code breaks
- docs can use `transitions` conceptually without lying

### 5. Introduce a serializable source artifact

Persist the source guest as a real artifact instead of only a Python authoring
file.

Working name:

- `*.mtm.source`

Payload should include:

- `TMProgram`
- `TMBand`
- `initial_state`
- `halt_state`
- optional descriptive metadata such as `name` / `note`

Format requirements:

- safe literal-assignment artifact format
- parsed via `ast.literal_eval` style machinery
- no `run_path` / arbitrary Python execution

Checkpoint:

- source artifact read/write round-trip test
- CLI can emit the source artifact from `.py`

### 6. Rename/generalize `TMRunConfig` to `RawTMInstance`

Use one raw program-plus-state object for both raw execution and recursive
guest compilation instead of adding a duplicate raw guest object.

Core fields:

- `program: TMTransitionProgram`
- `tape: dict[int, str]`
- `head: int`
- `state: str`

Checkpoint:

- object exists in the semantic/compiler surface
- tests cover minimal construction without `Encoding`

### 7. Add raw-guest ABI and encoding inference

Raw guests are not source guests. They may contain `L`, `S`, and `R` moves, so
their encoding/inference path must not assume the source-level `L` / `R`
restriction.

Deliverables:

- infer minimal `TMAbi` for:
  - `program.start_state`, `program.halt_state`, and current guest `state`
  - all transition source and target states
  - program alphabet, program blank, transition read/write symbols, and
    concrete tape symbols
  - raw guest directions actually used by the program
- support raw guest directions including `S`
- add a generic or dedicated helper such as:
  - `build_raw_guest_encoding(...)`

Important note:

- current host dispatch must intentionally treat “neither `L` nor `R`” as
  “stay put” for raw guests with `S` moves
- that behavior must be covered by a test so it does not remain accidental

Checkpoint:

- tests cover raw-guest encoding with `S` moves
- tests cover inferred `dir_width` when `S` is present

### 8. Implement the raw-guest compiler path

Compile already-lowered raw guests into the next-level UTM input.

Transformation:

```text
RawTMInstance
-> infer minimal TMAbi for raw states/symbols/tape
-> build Encoding for the raw guest
-> UTMEncoded
-> UTMBandArtifact
```

Raw guest tape conversion should mirror `TMBand.from_dict(...)` semantics:

- negative addresses -> `left_band`
- nonnegative addresses -> `right_band`
- include the current `head` cell even if that address currently holds blank

Checkpoint:

- can compile a trivial `TMTransitionProgram` guest into `.utm.band`
- resulting band is runnable by a lowered host

### 9. Add the `l1` / `l2` CLI workflow

Expose tower artifacts as a first-class workflow.

Desired flow:

```text
incrementer.py
  -> incrementer.mtm.source
  -> incrementer.l1.utm.band
  -> incrementer.l1.tm

incrementer.l1.tm + incrementer.l1.utm.band
  -> incrementer.l2.utm.band
  -> incrementer.l2.tm
```

Level meanings:

- `l1`: one UTM layer over the original source guest
- `l2`: one UTM layer over the `l1` raw host computation as guest

Checkpoint:

- CLI can produce `l1` artifacts from `.py`
- CLI can produce `l2` artifacts from `l1.tm + l1.utm.band`
- `l2` artifacts can be executed for bounded fuel without artifact,
  compatibility, or decode errors

## Non-Goals

Not in this tranche:

- redesigning `UniversalInterpreter` to be ABI-only rather than
  encoding-specialized
- replacing raw run-result dictionaries with a typed `RunResult`
- adding `artifact.decoded_view()` convenience APIs
- source-map or debugger metadata persistence in `.tm`

Those remain follow-up cleanups once `l2` works.

## Validation Strategy

At minimum, add tests for:

- `.tm` ABI metadata round-trip and backward compatibility
- ABI compatibility checks at run time
- compiler endpoint fallback order
- blank mismatch rejection
- grammar-version rejection
- source artifact round-trip
- `RawTMInstance` construction
- raw-guest encoding/inference with `S` moves
- raw-guest compile of a tiny program
- `l1` CLI artifact generation
- `l2` CLI artifact generation
- bounded-fuel execution of `l2` artifacts

## Recommended Execution Order

Implement in this exact order:

0. shared ABI literal/compatibility helpers
1. `.tm` ABI persistence
2. compiler/runtime correctness fixes
3. runtime compatibility checks
4. `TMTransitionProgram.transitions`
5. source artifact
6. `RawTMInstance`
7. raw-guest ABI/encoding inference
8. raw-guest compiler path
9. `l1` / `l2` CLI workflow
