# Object Model

This document describes the current object model for the Meta Turing Machine
project and the few missing objects that matter for future self-hosting work.

The key separation is:

- raw execution objects
- semantic decode objects
- persistent artifacts
- debugger read-model objects

Raw execution depends only on concrete symbols, states, tape cells, and move
directions. Semantic inspection depends on metadata:

- `TMAbi` for compatibility/family shape
- `Encoding` for decoded source-level meaning

## 1. Core Principles

### Raw vs Semantic

Raw execution requires:

- `TMTransitionProgram`
- runtime tape
- raw head
- raw state
- blank symbol

Semantic interpretation requires:

- `Encoding`
- UTM layout grammar
- encoded runtime tape or `UTMBandArtifact`

So:

- raw execution depends on neither `Encoding` nor `TMAbi`
- semantic decoding depends on `Encoding`
- compatibility checks depend on `TMAbi`

### Artifact Policy

The intended split is:

- `.utm.band` carries guest-specific encoding metadata
- `.tm` carries host-family ABI metadata, when known

The current implementation is close, but not fully there yet:

- `.utm.band` already persists `encoding`, `target_abi`, and `minimal_abi`
- `.tm` currently persists only raw execution data, not ABI metadata

## 2. Source Guest Objects

These objects describe the source machine being compiled into UTM input.

### `TMProgram`

Immutable source-level Turing machine transition program.

Current code:

- class: `mtm.source_encoding.TMProgram`
- fields:
  - `transitions`
  - `initial_state`
  - `halt_state`
  - `blank`

Transition shape:

```python
(state, read_symbol) -> (next_state, write_symbol, move_direction)
```

Source directions are currently:

```python
L = -1
R = 1
```

This is intentionally narrower than raw execution. Source programs do not
currently support `S` moves, while raw lowered programs do.

Responsibilities:

- expose source states and symbols
- validate source-level transitions
- support ABI inference for a source machine

### `TMBand`

Source-level tape/configuration for the object machine.

Current code:

- class: `mtm.semantic_objects.TMBand`
- fields:
  - `left_band`
  - `right_band`
  - `head`
  - `blank`

Meaning:

- `left_band` contains source cells at negative addresses, ordered left to right
- `right_band` contains source cells at addresses `0, 1, 2, ...`
- `head` is the simulated source-machine head address
- `blank` is the source machine blank symbol

Use `TMBand.from_dict(...)` when source addresses matter directly.

### `TMInstance`

Complete source guest input.

Current code:

- class: `mtm.semantic_objects.TMInstance`
- fields:
  - `program: TMProgram`
  - `band: TMBand`
  - `initial_state: str | None`
  - `halt_state: str | None`

This is a data bundle, not a behavior-heavy object. The compiler uses it as
input and resolves missing endpoints from the instance and compiler defaults.

## 3. ABI and Encoding Objects

### `TMAbi`

Universal-machine family shape.

Current code:

- class: `mtm.source_encoding.TMAbi`
- fields:
  - `state_width`
  - `symbol_width`
  - `dir_width`
  - `grammar_version`
  - `family_label`

Meaning:

- `state_width` is the encoded width of source states
- `symbol_width` is the encoded width of source symbols
- `dir_width` is the encoded width of move directions
- `grammar_version` names the marker/layout grammar
- `family_label` is a readable label such as `U[Wq=2,Ws=2,Wd=1]`

`TMAbi` is compatibility metadata. It describes the shape a universal-machine
family expects, but it is not enough by itself to decode source-level names.

### `Encoding`

Concrete assignment from source names to bitstrings under a selected ABI.

Current code:

- class: `mtm.source_encoding.Encoding`
- fields:
  - `state_ids`
  - `symbol_ids`
  - `direction_ids`
  - `state_width`
  - `symbol_width`
  - `direction_width`
  - `blank`
  - `initial_state`
  - `halt_state`

Responsibilities:

- encode source states, symbols, and directions
- decode source states, symbols, and directions through the stored maps
- preserve source-level meaning during UTM decode and debugging

`Encoding` is not required to execute the raw machine. It is required to say
what an encoded band means semantically.

## 4. Semantic Compiled Guest Objects

These objects describe the compiled guest before it is flattened into concrete
left/right UTM bands.

### `UTMRegisters`

Decoded semantic register block used by the universal interpreter.

Current code:

- class: `mtm.semantic_objects.UTMRegisters`
- fields:
  - `cur_state`
  - `cur_symbol`
  - `write_symbol`
  - `next_state`
  - `move_dir`
  - `halt_state`
  - `blank_symbol`
  - `left_dir`
  - `right_dir`
  - `cmp_flag`
  - `tmp_bits`

These registers now include both mutable execution state and guest-owned
constants copied from the band's encoding. `halt_state`, `blank_symbol`,
`left_dir`, and `right_dir` are part of the encoded register block so later
host logic can compare against the guest's actual field payloads instead of
baked host-width literals.

### `UTMEncodedRule`

One source transition rule after decoding from the UTM rule table.

Current code:

- class: `mtm.semantic_objects.UTMEncodedRule`
- fields:
  - `state`
  - `read_symbol`
  - `next_state`
  - `write_symbol`
  - `move_dir`

### `UTMSimulatedTape`

Decoded simulated source tape inside the UTM input.

Current code:

- class: `mtm.semantic_objects.UTMSimulatedTape`
- fields:
  - `left_band`
  - `right_band`
  - `head`
  - `blank`

### `UTMEncoded`

Semantic compiled guest.

Current code:

- class: `mtm.semantic_objects.UTMEncoded`
- fields:
  - `encoding: Encoding`
  - `registers: UTMRegisters`
  - `rules: tuple[UTMEncodedRule, ...]`
  - `simulated_tape: UTMSimulatedTape`
  - `minimal_abi: TMAbi`
  - `target_abi: TMAbi`

Responsibilities:

- expose the guest in semantic UTM form
- materialize a concrete `EncodedBand`
- emit a serializable `UTMBandArtifact`
- expose a `DecodedBandView`

Important methods:

```python
encoded.to_encoded_band() -> EncodedBand
encoded.to_band_artifact() -> UTMBandArtifact
encoded.decoded_view() -> DecodedBandView
```

## 5. Interpreter and Lowering IR

### `MetaASMProgram`

Semantic universal interpreter program in Meta-ASM form.

Current code:

- actual type: `mtm.meta_asm.Program`
- produced by:
  - `build_universal_meta_asm(encoding)`
  - `UniversalInterpreter.to_meta_asm()`

This is still a real and desirable IR layer:

- human-readable
- source-map-friendly
- useful for teaching and debugging
- lowered later into raw `.tm`

`.asm` is currently best described as the textual export of this IR, not as a
fully round-trippable persisted artifact with its own rich object layer.

### `UniversalInterpreter`

Facade for “the universal machine for this encoded guest”.

Current code:

- class: `mtm.universal.UniversalInterpreter`
- constructors:
  - `for_encoding(encoding)`
  - `for_encoded(encoded_or_band_artifact)`

Important methods:

```python
interpreter.to_meta_asm() -> Program
interpreter.alphabet_for_band(band_artifact) -> tuple[str, ...]
interpreter.lower(alphabet, ...) -> UTMProgramArtifact
interpreter.lower_for_band(band_artifact, ...) -> UTMProgramArtifact
interpreter.run(band_artifact, fuel=...) -> dict[str, object]
```

Important note:

`UniversalInterpreter` is currently specialized to a concrete `Encoding`, not
just a `TMAbi`. The emitted host program embeds concrete encoded constants such
as halt-state bits and direction bits.

### `TransitionSourceMap`

Lookup from raw transition rows back to lowered source structure.

Current code:

- class: `mtm.lowering.source_map.TransitionSourceMap`

Responsibilities:

- preserve `.asm -> .tm` provenance
- support debugger explanations and grouped stepping

## 6. Raw Execution Objects

### `TMTransitionProgram`

Generic raw ordinary transition table.

Current code:

- class: `mtm.raw_transition_tm.TMTransitionProgram`
- fields:
  - `prog`
  - `start_state`
  - `halt_state`
  - `alphabet`
  - `blank`

Conceptually, `prog` is the transition relation:

```python
(state, read_symbol) -> (next_state, write_symbol, move_direction)
```

Raw directions are:

```python
L = -1
S = 0
R = 1
```

This is the runner-facing executable object.

### `RawTMInstance`

A raw transition program paired with its current tape/head/state.

Current code:

- class: `mtm.semantic_objects.RawTMInstance`
- fields:
  - `program`
  - `tape`
  - `head`
  - `state`

Execution fields:

- `program` is the raw executable
- `tape` maps integer addresses to concrete runtime symbols
- `head` is the raw head position
- `state` is the raw control state

Uses:

- runner-facing raw execution configuration
- recursive-self-hosting guest input for compiling a raw machine into another
  UTM layer

### Raw Run Result

Current raw runners return dictionaries, not a first-class `RunResult`
dataclass. The common shape is:

```python
{
    "status": "halted" | "stuck" | "fuel_exhausted",
    "state": ...,
    "head": ...,
    "tape": ...,
    "steps": ...,
}
```

A typed `RunResult` object is still a plausible future cleanup, but it is not
the current API.

## 7. Persistent Artifacts

### `UTMBandArtifact`

Serializable encoded guest input emitted as `*.utm.band`.

Current code:

- class: `mtm.semantic_objects.UTMBandArtifact`
- fields:
  - `encoding`
  - `left_band`
  - `right_band`
  - `start_head`
  - `target_abi`
  - `minimal_abi`

Responsibilities:

- serialize and deserialize the guest input artifact
- materialize the runtime tape
- pair that tape with a raw host program
- support semantic decode/debug

Important methods:

```python
artifact.to_encoded_band() -> EncodedBand
artifact.to_runtime_tape() -> dict[int, str]
artifact.to_raw_instance(program_artifact_or_tm) -> RawTMInstance
artifact.write(path) -> None
UTMBandArtifact.read(path) -> UTMBandArtifact
```

Current file-level format versioning lives in the artifact text as:

```text
format = "mtm-utm-band-v1"
```

not as an object field.

### `.utm.band` Metadata Policy

`.utm.band` is both:

- executable encoded input
- self-describing semantic/debug artifact

It should carry:

- concrete encoded band contents
- `Encoding`
- `target_abi`
- `minimal_abi`
- file format version

### `UTMProgramArtifact`

Typed wrapper around a raw `.tm` when used as the host universal machine.

Current code:

- class: `mtm.semantic_objects.UTMProgramArtifact`
- fields:
  - `program: TMTransitionProgram`
  - `target_abi: TMAbi | None`
  - `minimal_abi: TMAbi | None`

Important methods:

```python
program_artifact.write(path) -> None
program_artifact.run(band_artifact, fuel=...) -> dict[str, object]
```

Current limitation:

- the in-memory object can carry ABI metadata
- current `.tm` serialization does not round-trip that metadata

### `.tm` Metadata Policy

`.tm` is the raw executable host program.

Raw execution should require only:

- `raw_tm`
- `start_state`
- `halt_state`
- `alphabet`
- `blank`

ABI on `.tm` is useful as compatibility/provenance metadata, but must not be
an execution dependency.

So the intended policy is:

- `.tm` carries host-family ABI metadata, when known
- raw execution depends on neither encoding nor ABI

Current implementation still writes only raw execution data.

### `ASM` Text Export

Current CLI can emit textual Meta-ASM:

```text
asm_out = format_program(interpreter.to_meta_asm())
```

This is a useful persistent inspection/export form, but it is not currently a
rich typed artifact with a stable parser and round-trip contract.

## 8. Debugger Read Model

The debugger no longer centers its UI around bespoke summary objects. Its core
execution object is the raw trace, and the UI is derived from facts and
queries.

### `RawTraceRunner`

Reversible debugger over a `TMTransitionProgram`.

Responsibilities:

- step and rewind one raw row at a time
- expose next and last raw transitions
- use `TransitionSourceMap` when available
- group raw execution into routine, instruction, block, or source-step moves
- optionally decode semantic views when an `Encoding` is available

### `RawTraceView`

Projection of raw, source-mapped, and semantic state.

Current code:

- class: `mtm.debugger.trace.RawTraceView`
- fields:
  - `snapshot`
  - `next_raw_transition_key`
  - `next_raw_transition_row`
  - `next_raw_transition_source`
  - `last_transition`
  - `last_transition_source`
  - `decoded_view`
  - `decode_error`

### `TraceFacts`, `DebuggerQueries`, presentation documents

These are debugger read-model objects, not compiler-domain objects.

Responsibilities:

- materialize trace-derived facts
- answer typed debugger queries such as `status`, `where`, and `view`
- build presentation documents for plain-text and Rich renderers

## 9. Compiler Facade

### `Compiler`

Compiler from source guest objects into semantic UTM input.

Current code:

- class: `mtm.compiler.Compiler`

Important methods:

```python
Compiler(target_abi: TMAbi | None = None, initial_state: str | None = None, halt_state: str | None = None)
Compiler.infer_abi(instance: TMInstance) -> TMAbi
compiler.compile(instance: TMInstance) -> UTMEncoded
```

Current compilation path:

```text
TMInstance
-> inferred minimal TMAbi
-> selected target TMAbi
-> Encoding
-> UTMEncoded
-> EncodedBand / UTMBandArtifact
```

## 10. Current Primary Workflow

```python
instance = TMInstance(program, band, initial_state=..., halt_state=...)

compiler = Compiler(target_abi=abi)
encoded = compiler.compile(instance)

band_artifact = encoded.to_band_artifact()
band_artifact.write("incrementer.utm.band")

interpreter = UniversalInterpreter.for_encoded(encoded)
program_artifact = interpreter.lower_for_band(band_artifact)
program_artifact.write("utm.tm")

result = program_artifact.run(band_artifact, fuel=100_000)
```

## 11. Missing Objects That Still Matter

Two missing abstractions now matter more than any large artifact hierarchy.

### `SourceArtifact`

The project still lacks a real serializable source-level bundle corresponding
to today’s authoring-time `.py` input:

- `TMProgram`
- `TMBand`
- `initial_state`
- `halt_state`
- optional `name` / `note`

Today `.py` is an authoring format, not a stable source artifact format.

### `RawTMInstance`

This is the key abstraction for recursive self-hosting.

Conceptually:

- `TMInstance` = symbolic source guest
- `RawTMInstance` = already-lowered ordinary TM guest

`RawTMInstance` contains:

- `program: TMTransitionProgram`
- `tape: dict[int, str]`
- `head: int`
- `state: str`

The current compiler compiles source guests into UTM input. Recursive
self-hosting requires a second compiler path that compiles raw guests into UTM
input.

## 12. Known Gaps

The sections above describe the intended current object contract. The
implementation is close, but a few important gaps remain:

### Compiler state fallback

`Compiler` currently resolves `initial_state` and `halt_state` from:

- `TMInstance`
- `Compiler` defaults

It does not yet fall back to `TMProgram.initial_state` or
`TMProgram.halt_state`, even though those fields exist on `TMProgram`.

### ABI grammar-version validation

The current compiler validates ABI field widths, but does not yet enforce
`grammar_version` equality when checking whether a selected `TMAbi` is
compatible with the inferred minimal ABI.

### Source blank consistency

A source guest should be well-formed only when:

```text
TMProgram.blank == TMBand.blank
```

Current compilation logic uses the band blank as the concrete blank during
encoding and does not yet validate that the program and band blanks agree.

### `.tm` metadata persistence

The intended policy is that `.tm` may carry host-family ABI metadata when
known. Current `.tm` serialization still stores only:

- raw transition table
- start state
- halt state
- alphabet
- blank symbol

In-memory `UTMProgramArtifact` objects can carry `target_abi` and
`minimal_abi`, but that metadata does not yet round-trip through persisted
`.tm` files.

### Artifact compatibility checks

When both `.tm` and `.utm.band` carry ABI metadata, tooling should reject
mismatched:

- `grammar_version`
- `state_width`
- `symbol_width`
- `dir_width`

before execution starts. Current runtime paths do not yet enforce that check.

### Decode entry points

`UTMBandArtifact` supports semantic decode and debugging through helper
functions after conversion to `EncodedBand`, but it does not yet expose a
direct artifact-level method such as `artifact.decoded_view()`.

### Typed run results

Raw execution currently returns plain dictionaries with keys like `status`,
`state`, `head`, `tape`, and `steps`. A first-class typed `RunResult` object is
still a possible cleanup, but it is not the current API.

## 13. Short Mapping

- `TMProgram` = source transition semantics
- `TMBand` = source input tape/configuration
- `TMInstance` = source guest bundle
- `TMAbi` = universal-machine family shape
- `Encoding` = concrete source-name-to-bitstring mapping
- `UTMEncoded` = semantic compiled guest
- `UTMBandArtifact` = emitted encoded guest input
- `MetaASMProgram` = semantic universal interpreter IR
- `UTMProgramArtifact` = typed wrapper around a host `.tm`
- `TMTransitionProgram` = raw executable transition table
- `RawTMInstance` = raw program plus tape/head/state, used for running and recursive guest compilation
- `DecodedBandView` = decoded semantic inspection view
- `TransitionSourceMap` = raw-row-to-lowered-source provenance
- `RawTraceRunner` = reversible raw debugger
- `TraceFacts` / `DebuggerQueries` = debugger read model
- `SourceArtifact` = missing serializable source guest format
