# Object Model

This document defines the semantic and artifact objects for the Meta Turing
Machine project.

The project has two products:

- a universal-machine program emitted as `utm.tm`
- an encoded input band emitted as `*.utm.band`

The emitted `utm.tm` program runs over the emitted `.utm.band` input. Together
they let an ordinary TM runner simulate a source-level object TM.

## 1. Source Objects

### `TMProgram`

Source-level Turing machine program.

Fields:

- `transitions`
- `initial_state`
- `halt_state`
- `blank`

Transition shape:

```python
(state, read_symbol) -> (next_state, write_symbol, move_direction)
```

Directions:

```python
L = -1
R = 1
```

Responsibilities:

- expose the source states and symbols
- validate transition directions
- provide source-level transition lookup
- report the ABI required by a paired source band

### `TMBand`

Source-level demonstrational tape/configuration.

Fields:

- `left_band`
- `right_band`
- `head`
- `blank`

Meaning:

- `left_band` contains source cells at negative addresses, ordered left to right
- `right_band` contains source cells at addresses `0, 1, 2, ...`
- `head` is the simulated object-machine head address
- `blank` is the source machine's blank symbol

Use `TMBand.from_dict(...)` when source addresses matter directly.
UTM input artifact supplies explicit blank padding when a larger simulated
window is needed.

### `TMInstance`

Source program plus source band.

Fields:

- `program: TMProgram`
- `band: TMBand`

Responsibilities:

- infer the minimal ABI requirement for this exact program and band
- provide the input to the object compiler

## 2. ABI and Encoding

### `TMAbi`

Target universal-machine family.

Fields:

- `state_width`
- `symbol_width`
- `dir_width`
- `grammar_version`
- `family_label`

Meaning:

- `state_width` is the bit width for encoded source states
- `symbol_width` is the bit width for encoded source symbols
- `dir_width` is the bit width for encoded movement directions
- `grammar_version` identifies the marker/layout grammar
- `family_label` is a readable label such as `U[Wq=8,Ws=8,Wd=1]`

The compiler infers a minimal `TMAbi` for each source instance. A selected
target `TMAbi` must be wide enough for that instance:

```text
selected_abi.state_width >= required.state_width
selected_abi.symbol_width >= required.symbol_width
selected_abi.dir_width >= required.dir_width
selected_abi.grammar_version == required.grammar_version
```

### `Encoding`

Dense concrete assignment from source names to bitstrings under a selected ABI.

Fields:

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

- encode and decode source states
- encode and decode source symbols
- encode and decode directions
- preserve the property `decode(encode(x)) == x`

Dense interning is the default assignment strategy. The blank symbol is always
assigned id `0`, so its encoded bitstring is all zeroes at the selected symbol
width.

## 3. Semantic UTM Object

### `UTMRegisters`

Semantic register block used by the universal interpreter.

Fields:

- `cur_state`
- `cur_symbol`
- `write_symbol`
- `next_state`
- `move_dir`
- `cmp_flag`
- `tmp_bits`

### `UTMEncodedRule`

One encoded object-program transition rule.

Fields:

- `state`
- `read_symbol`
- `next_state`
- `write_symbol`
- `move_dir`

Meaning:

```text
(state, read_symbol) -> (next_state, write_symbol, move_dir)
```

### `UTMSimulatedTape`

Semantic simulated object tape inside the UTM input.

Fields:

- `left_band`
- `right_band`
- `head`
- `blank`

### `UTMEncoded`

Semantic compiled object consumed by the universal-machine family.

Fields:

- `encoding: Encoding`
- `registers: UTMRegisters`
- `rules: tuple[UTMEncodedRule, ...]`
- `simulated_tape: UTMSimulatedTape`
- `minimal_abi: TMAbi`
- `target_abi: TMAbi`

Responsibilities:

- expose the UTM-side semantic state
- emit a concrete `UTMBandArtifact`
- expose a decoded semantic view for debugging

Expected methods:

```python
encoded.to_band_artifact() -> UTMBandArtifact
encoded.decoded_view() -> DecodedBandView
```

## 4. Artifact Objects

### `UTMBandArtifact`

Concrete encoded UTM input band emitted as `*.utm.band`.

Fields:

- `encoding`
- `left_band`
- `right_band`
- `start_head`
- `target_abi`
- `minimal_abi`
- `artifact_version`

Layout:

```text
negative addresses:  left band  = negative simulated tape + registers + rules
nonnegative addresses: right band = nonnegative simulated tape
```

The split point is between address `-1` and address `0`. The right band starts
at address `0`. The left band is materialized toward negative addresses and
contains `#END_TAPE_LEFT ... #TAPE_LEFT` around the negative simulated tape.
`#TAPE_LEFT` stays fixed next to the registry/rule area; `#END_TAPE_LEFT`
moves left when the simulated tape grows.

Responsibilities:

- serialize and deserialize the `.utm.band` file
- materialize the runner-facing runtime tape
- create a run configuration when paired with a UTM program artifact
- decode back into `UTMEncoded` when semantic inspection is needed

Expected methods:

```python
artifact.to_runtime_tape() -> dict[int, str]
artifact.to_run_config(program: UTMProgramArtifact) -> TMRunConfig
artifact.write(path) -> None
UTMBandArtifact.read(path) -> UTMBandArtifact
```

### `ASMArtifact`

Text artifact for the generated Meta-ASM universal interpreter.

Fields:

- `text`
- `abi`
- optional comments or source annotations

Typical extension:

```text
.asm
```

### `UTMProgramArtifact`

Lowered universal-machine program emitted as `utm.tm`.

Fields:

- `program: TMTransitionProgram`
- `abi`
- optional lowering/debug metadata

Responsibilities:

- serialize and deserialize the `.tm` file
- run against a matching `UTMBandArtifact`

Expected methods:

```python
program_artifact.write(path) -> None
UTMProgramArtifact.read(path) -> UTMProgramArtifact
program_artifact.run(band_artifact, fuel=...) -> RunResult
```

### `TMTransitionProgram`

Generic flat ordinary TM transition table.

Fields:

- `transitions`
- `start_state`
- `halt_state`
- `alphabet`
- `blank`

Transition shape:

```python
(state, read_symbol) -> (next_state, write_symbol, move_direction)
```

This object is generic. A `UTMProgramArtifact` is the UTM-specific artifact
that owns one of these programs.

## 5. Runtime Objects

### `TMRunConfig`

Runner-facing configuration for an ordinary TM transition program.

Fields:

- `tape`
- `head`
- `state`

Meaning:

- `tape` maps integer addresses to symbols
- `head` is the raw runner head address
- `state` is the raw runner control state

### `RunResult`

Result of running a `TMTransitionProgram`.

Fields:

- `status`
- `state`
- `head`
- `tape`
- `steps`

Expected statuses:

- `halted`
- `stuck`
- `fuel_exhausted`

### `DecodedBandView`

Human-readable semantic view recovered from a UTM runtime tape or band artifact.

Fields:

- `registers`
- `rules`
- `simulated_tape`
- `encoding`

Responsibilities:

- report the simulated source state
- report the simulated source head
- expose decoded source-level tape cells and transition rules

## 6. Debugger Objects

### `TransitionSourceMap`

Lookup table from a concrete raw row `(state, read_symbol)` to
`RawTransitionSource`.

Responsibilities:

- preserve where a lowered raw row came from
- support debugger projections from raw execution back to source structure

### `RawTraceRunner`

Reversible debugger over a `TMTransitionProgram`.

Responsibilities:

- step and rewind one raw TM row at a time
- expose the next raw row and the last executed raw row
- use `TransitionSourceMap` for source-aware stepping when available
- group raw execution into routine, instruction, block, or source-step moves

### `RawTraceView`

Teaching-facing projection of a `RawTraceRunner`.

Fields:

- `snapshot`
- `next_raw_transition_key`
- `next_raw_transition_row`
- `next_raw_transition_source`
- `last_transition`
- `last_transition_source`
- `decoded_view`
- `decode_error`

Meaning:

- raw fields explain the concrete interpreter state
- source fields explain which lowered source structure the row belongs to
- `decoded_view` explains the simulated source-machine state when the runtime
  tape can be decoded under an `Encoding`

## 7. Compiler and Interpreter Objects

### `Compiler`

Object compiler from a source `TMInstance` to `UTMEncoded`.

Expected interface:

```python
Compiler(target_abi: TMAbi | None = None)
Compiler.infer_abi(instance: TMInstance) -> TMAbi
compiler.compile(instance: TMInstance) -> UTMEncoded
```

Compilation stages:

```text
TMInstance
-> minimal TMAbi
-> Encoding
-> UTMEncoded
-> UTMBandArtifact
```

### `UniversalInterpreter`

Factory for the UTM interpreter for a selected ABI.

Expected interface:

```python
UniversalInterpreter.for_abi(abi: TMAbi) -> UniversalInterpreter
interpreter.to_meta_asm() -> MetaASMProgram
interpreter.to_program_artifact() -> UTMProgramArtifact
```

### `MetaASMProgram`

Semantic universal interpreter program in Meta-ASM form.

Fields:

- `abi`
- `blocks`
- `entry_label`

Responsibilities:

- format as `.asm`
- execute in the host Meta-ASM interpreter for reference runs
- lower to a `TMTransitionProgram`

Expected methods:

```python
asm.format() -> str
asm.run_host(band_artifact, fuel=...) -> RunResult
asm.lower() -> TMTransitionProgram
```

## 8. Primary Workflow

```python
instance = TMInstance(program, band)

compiler = Compiler(target_abi=abi)
encoded = compiler.compile(instance)

band_artifact = encoded.to_band_artifact()
band_artifact.write("incrementer.utm.band")

interpreter = UniversalInterpreter.for_abi(encoded.target_abi)
asm = interpreter.to_meta_asm()
program_artifact = asm.lower().to_artifact()
program_artifact.write("utm.tm")

result = program_artifact.run(band_artifact, fuel=100_000)
view = result.decode(encoded.encoding)
```

## 9. Object Responsibilities

Short mapping:

- `TMProgram` = source transition semantics
- `TMBand` = source input tape/configuration
- `TMInstance` = source program plus source input
- `TMAbi` = selected universal-machine family
- `Encoding` = dense source-name-to-bitstring assignment
- `UTMEncoded` = semantic UTM input object
- `UTMBandArtifact` = emitted `.utm.band` input
- `MetaASMProgram` = semantic universal interpreter in Meta-ASM
- `UTMProgramArtifact` = emitted `utm.tm`
- `TMTransitionProgram` = generic ordinary transition table
- `TMRunConfig` = runner-facing tape/head/state
- `DecodedBandView` = semantic inspection view
- `TransitionSourceMap` = raw-row-to-lowered-source lookup
- `RawTraceRunner` = reversible raw debugger with grouped stepping
- `RawTraceView` = debugger projection for raw plus semantic inspection
