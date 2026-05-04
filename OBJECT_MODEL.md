# Object Model

This document describes the intended conceptual object model for the Meta Turing Machine project.

The main goal is to separate:

1. source-level TM semantics
2. semantic UTM-side encoded objects
3. serialized artifacts
4. runtime execution state
5. decoded semantic views

The important correction is this:

- `outer_tape` is not the center of the model
- `outer_tape` is an execution/serialization representation
- the semantic compiled object should be modeled separately


## 1. Source Layer

### `TMProgram`

Pure source-level Turing machine semantics.

Fields:

- `transitions`
- `initial_state`
- `halt_state`
- `blank`

Shape:

```python
(state, read_symbol) -> (next_state, write_symbol, move_direction)
```

Notes:

- `TMProgram` should not carry ABI or encoding concerns.
- It is the source program, not a compiled artifact.


### `TMBand`

Generic source-level tape/configuration.

This replaces the weaker idea of raw `input_symbols`.

Fields:

- `cells`
- `head`
- `blank`

Notes:

- `TMBand` is not UTM-specific.
- It is the natural tape/configuration object paired with a `TMProgram`.


### `TMInstance`

Optional source-level aggregate.

Fields:

- `program: TMProgram`
- `band: TMBand`

Meaning:

```text
TMInstance = TMProgram + TMBand
```


## 2. ABI Layer

### `TMAbi`

Target encoding family / machine family.

Fields:

- `state_width`
- `symbol_width`
- `dir_width`
- `grammar_version`
- optional reserved temporary symbols
- optional family label, for example `U[Wq=8,Ws=8,Wd=1]`

Meaning:

- this is the family against which a UTM-side encoding or UTM program is built


### `AbiRequirement`

Minimum ABI required by a source program/configuration.

This may use the same concrete type as `TMAbi`, but conceptually it means:

- what is minimally needed
- not necessarily what was actually chosen for encoding


## 3. Encoding Layer

### `Encoding`

Concrete dense assignment of IDs and bit widths under a chosen ABI.

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

Meaning:

- this is where source-level names become concrete bitstrings
- this is derived from source objects plus a chosen target ABI


## 4. Semantic UTM Input Layer

### `UTMEncoded`

Semantic compiled object for the universal machine.

This is the important UTM-facing semantic object.

It should be modeled in terms of meaning, not in terms of raw `outer_tape` first.

Fields:

- `encoding: Encoding`
- `registers`
- `rules`
- `simulated_tape`
- `simulated_head`
- `minimal_abi`
- `target_abi`
- optional grammar/version metadata

Meaning:

- `registers` are the semantic global memory of the universal interpreter
- `rules` are the encoded object-program transition registry
- `simulated_tape` is the semantic object-tape image being interpreted
- `simulated_head` is the source-level object-head position inside that semantic tape

Notes:

- `UTMEncoded` is the semantic compiled object
- it is not yet the final serialized artifact


## 5. Serialized Artifact Layer

### `UTMEncodingArtifact`

Serialized artifact form of `UTMEncoded`.

Fields:

- `encoding`
- `left_band`
- `right_band`
- `start_head`
- `target_abi`
- `minimal_abi`
- optional artifact version

Meaning:

- this is the concrete `.utm`-style object image
- `left_band` / `right_band` belong here as serialization layout
- `start_head` is launch metadata for the raw UTM runner
- they are not the primary semantic object

Notes:

- you should be able to decode:

```text
UTMEncodingArtifact -> UTMEncoded
```

- and also re-encode:

```text
UTMEncoded -> UTMEncodingArtifact
```


### `ASMArtifact`

Serialized artifact form of the Meta-ASM universal interpreter.

Fields:

- textual ASM
- optional ABI metadata
- optional comments / annotations

Meaning:

- this corresponds to a `.asm` output


### `TMArtifact`

Serialized artifact form of a lowered raw TM program.

Fields:

- transitions
- start state
- halt state
- alphabet
- ABI metadata
- optional debug / lowering metadata

Meaning:

- this corresponds to a `.tm` output


## 6. Universal Interpreter Program Layer

### `MetaASMProgram`

Width-specialized universal interpreter in Meta-ASM form.

Fields:

- `abi`
- `blocks`
- `entry_label`
- optional comments / source annotations

Meaning:

- this is the semantic universal interpreter program
- it is still not raw TM


### `RawTMProgram`

Lowered ordinary TM transition program.

Fields:

- `transitions`
- `start_state`
- `halt_state`
- `alphabet`
- `abi`
- optional lowering/debug metadata

Meaning:

- this is the runnable UTM program
- this is the thing emitted as `utm.tm`

Notes:

- the concrete lowering depends on the target ABI
- and on the chosen outer alphabet / marker set


## 7. Runtime Layer

### `RawTMConfig`

Runner-facing machine configuration.

Fields:

- `program: RawTMProgram`
- `tape`
- `head`
- `state`

Meaning:

- this is execution state
- this is where runner-level things like concrete tape maps belong

This is where a representation like `outer_tape` belongs if it is used by the raw TM runner.

That is why `outer_tape` should not be the conceptual center of the artifact model.


## 8. Decoded Semantic View Layer

### `DecodedBandView`

Human-meaningful interpretation of UTM execution state.

Fields:

- decoded registers
- decoded rule registry
- decoded simulated tape
- `simulated_head` accessor
- `current_state` accessor

Meaning:

- this is how we recover the semantics we care about from raw UTM execution
- this should be a first-class object, not just pretty-printer logic


## 9. Compatibility Rules

There are two different notions of compatibility.

### Source-Level Compatibility

Question:

```text
Could this source program/configuration fit in this UTM family?
```

Rule:

```text
UTM.abi >= UTMEncoded.minimal_abi
```

This is about semantic fit.


### Artifact-Level Compatibility

Question:

```text
Can this exact serialized artifact be run by this exact UTM program?
```

Rule:

```text
UTM.abi must understand UTMEncodingArtifact.target_abi
```

In the simplest current model, this is effectively:

```text
UTM.abi == UTMEncodingArtifact.target_abi
```

because once the bits are laid out, the concrete field widths are fixed.


## 10. Pipeline

The intended conceptual pipeline is:

```text
TMProgram + TMBand
-> infer minimal ABI

TMProgram + TMBand + target ABI
-> Encoding
-> UTMEncoded
-> UTMEncodingArtifact

target ABI + outer alphabet / marker set
-> MetaASMProgram
-> RawTMProgram
-> TMArtifact

TMArtifact + UTMEncodingArtifact
-> RawTMConfig
-> execution
-> DecodedBandView
```


## 11. Intuition

Short mapping:

- `TMProgram` = source semantics
- `TMBand` = source-level tape/configuration
- `TMAbi` = target family
- `Encoding` = concrete bit-level naming
- `UTMEncoded` = semantic compiled object for the UTM
- `UTMEncodingArtifact` = serialized `.utm`
- `MetaASMProgram` = semantic universal interpreter
- `RawTMProgram` = runnable UTM
- `TMArtifact` = serialized `.tm`
- `RawTMConfig` = runtime execution state
- `DecodedBandView` = semantic debugger / decoder


## 12. Design Principles

1. Keep `TMProgram` pure.
   ABI and encoding belong to compilation, not source semantics.

2. Prefer explicit ABI objects over hidden width inference in the main pipeline.
   Width inference should exist, but as a helper step.

3. Treat `UTMEncoded` as the primary semantic UTM-side object.
   Treat `UTMEncodingArtifact` as serialization.

4. Keep artifact objects and runtime objects separate.
   A serialized image is not the same thing as a runner configuration.

5. Make decoding explicit.
   Recovering semantic meaning from UTM execution should be modeled directly.

6. Keep source compatibility and artifact compatibility separate.
   They are related, but not identical.
