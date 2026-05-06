---
title: Overview
audience: implementers
---

# Overview

## 1. Goal

Build a staged system where a source-level Turing machine is compiled into an
encoded UTM input band, and a generated universal interpreter executes that band
on an ordinary TM runner.

The two primary emitted runtime artifacts are:

```text
object.l1.tm        lowered universal-machine transition program for level 1
object.l1.utm.band  encoded guest input band for level 1
```

Execution pairs them as:

```text
ordinary TM runner
  program: object.l1.tm
  input:   object.l1.utm.band
```

There are two compilation pipelines:

```text
Source-guest compiler:
  TMInstance
  -> UTMEncoded
  -> UTMBandArtifact

Universal interpreter compiler:
  Encoding
  -> MetaASMProgram
  -> TMTransitionProgram
  -> UTMProgramArtifact
```

The current compiler handles source guests. Recursive self-hosting requires a
second path for raw guests:

```text
Raw-guest compiler:
  RawTMInstance
  -> UTMEncoded
  -> UTMBandArtifact
```

## 2. Intuition

A Turing Machine (TM) has declared operations and an infinite tape with squares
on it that the machine can read and rewrite based on the declared operations.

A Universal Turing Machine (UTM) is a set of declared operations that run on a
tape that has other Turing Machines on it.

## 3. UTM in MTM

In this repository, we have an Assembly Language specifically designed to
generate UTMs, where the UTM encoding has a fixed size for representing states,
symbols, and directions.

The tuple `(state_width, symbol_width, dir_width, grammar_version)` forms an
Application Binary Interface (ABI).

An encoded TM with:

```text
band_abi = (
  state_width  = tm_state_width,
  symbol_width = tm_symbol_width,
  dir_width    = tm_dir_width,
  grammar_version = tm_grammar_version
)
```

can run on a given UTM with:

```text
host_abi = (
  state_width  = utm_state_width,
  symbol_width = utm_symbol_width,
  dir_width    = utm_dir_width,
  grammar_version = utm_grammar_version
)
```

only if:

```text
tm_state_width  <= utm_state_width
tm_symbol_width <= utm_symbol_width
tm_dir_width    <= utm_dir_width
tm_grammar_version == utm_grammar_version
```

In other words:

```text
band_abi <= host_abi  => executable
band_abi > host_abi   => rejected before execution
```

This is done to reduce state space and have machines that are easier to
understand, debug, and run.

## 4. Components

MTM is organized as a staged compiler and execution pipeline.

### Source Guest Layer

Source-level machine definition:

```text
TMProgram
  + TMBand
  + initial_state
  + halt_state
    ↓
TMInstance
```

Responsibilities:

* define source transition semantics
* define the initial simulated source tape
* define source-machine start and halt states

---

### ABI and Encoding Layer

The compiler first selects or validates a compatible ABI family:

```text
TMInstance
    ↓ infer / validate
TMAbi
```

```text
TMAbi = (
  state_width,
  symbol_width,
  dir_width,
  grammar_version
)
```

Then a concrete guest encoding is constructed:

```text
TMInstance
  + TMAbi
    ↓
Encoding
```

Responsibilities:

* assign source states to bitstrings
* assign source symbols to bitstrings
* assign move directions to bitstrings
* preserve semantic decode information

---

### Source Guest Compiler

The source guest compiler transforms a symbolic source machine into semantic
UTM input:

```text
TMInstance
    ↓ Compiler.compile(...)
UTMEncoded
```

```text
UTMEncoded
  = registers
  + encoded rules
  + simulated tape
  + Encoding
  + ABI metadata
```

Responsibilities:

* encode source rules
* encode the simulated source tape
* initialize UTM registers
* produce semantic UTM state

---

### Encoded UTM Band

The semantic UTM object is flattened into a concrete encoded runtime band:

```text
UTMEncoded
    ↓ to_band_artifact()
UTMBandArtifact
```

Artifact output:

```text
object.l1.utm.band
```

The encoded band contains:

```text
negative simulated tape
+ #TAPE_LEFT
+ registers
+ encoded transition rules
+ nonnegative simulated tape
```

Responsibilities:

* persist encoded guest input
* materialize runtime tape
* preserve semantic decode metadata
* preserve ABI compatibility metadata

---

### Universal Interpreter Generator

The universal interpreter is generated for a selected encoding / ABI family:

```text
Encoding
    ↓
UniversalInterpreter
    ↓ to_meta_asm()
MetaASMProgram
```

Responsibilities:

* generate the semantic universal-machine interpreter
* specialize interpreter routines to bounded field widths
* expose human-readable Meta-ASM IR

---

### Meta-ASM Lowering Pipeline

The semantic interpreter is lowered into an ordinary TM transition table:

```text
MetaASMProgram
    ↓
Routine
    ↓
RoutineCFG
    ↓
TMBuilder
    ↓
TMTransitionProgram
```

Artifact output:

```text
object.l1.tm
```

Responsibilities:

* lower Meta-ASM instructions
* construct raw TM states and transitions
* validate CFG correctness
* emit executable ordinary TM transition tables

---

### Host Program Artifact

The lowered raw host program is wrapped as a persistent executable artifact:

```text
TMTransitionProgram
    ↓
UTMProgramArtifact
```

Responsibilities:

* persist raw executable transition tables
* optionally persist host ABI metadata
* execute encoded UTM bands

---

### Raw Execution Layer

Execution uses only raw execution objects:

```text
UTMProgramArtifact
  + UTMBandArtifact
    ↓
RawTMInstance
    ↓
ordinary TM runner
```

Execution pairing:

```text
program: object.l1.tm
input:   object.l1.utm.band
```

Raw execution requires only:

* raw transition table
* runtime tape
* raw state
* raw head
* blank symbol

It does not require semantic encoding metadata.

---

### Semantic Decode Layer

Semantic inspection reconstructs source-level meaning from encoded runtime
state:

```text
EncodedBand
  + Encoding
    ↓
DecodedBandView
```

Responsibilities:

* decode source states
* decode source symbols
* decode simulated tape contents
* decode UTM registers and rule tables

---

### Recursive Raw Guest Compilation

Already-lowered ordinary TMs can themselves become guests:

```text
TMTransitionProgram
  + runtime tape
  + raw head/state
    ↓
RawTMInstance
    ↓ compile_raw_guest(...)
UTMEncoded
    ↓
UTMBandArtifact
```

This is the recursive self-hosting path used for:

```text
l1 -> l2 -> l3 -> ...
```

Example:

```text
incrementer.l1.tm
  + incrementer.l1.utm.band runtime tape
    ↓
incrementer.l2.utm.band
```

---

### Debugger and Trace Layer

The debugger operates over raw execution plus semantic decode metadata:

```text
TMTransitionProgram
  + runtime tape
  + TransitionSourceMap
    ↓
RawTraceRunner
    ↓
TraceFacts
    ↓
DebuggerQueries
```

Responsibilities:

* reversible stepping
* grouped stepping by routine/instruction/source step
* semantic decode views
* lowered-source provenance tracking

## 5. Public Interface

The current top-level workflow is:

```python
instance = TMInstance(program, band, initial_state=..., halt_state=...)

compiler = Compiler(target_abi=abi)
encoded = compiler.compile(instance)

band_artifact = encoded.to_band_artifact()
band_artifact.write("object.l1.utm.band")

interpreter = UniversalInterpreter.for_encoded(encoded)
asm = interpreter.to_meta_asm()
program_artifact = interpreter.lower_for_band(band_artifact)
program_artifact.write("object.l1.tm")

result = program_artifact.run(band_artifact, fuel=100_000)
```

Primary objects:

- `TMProgram`
- `TMBand`
- `TMInstance`
- `TMAbi`
- `Encoding`
- `Compiler`
- `UTMEncoded`
- `UTMBandArtifact`
- `UniversalInterpreter`
- `MetaASMProgram`
- `TMTransitionProgram`
- `UTMProgramArtifact`
- `RawTMInstance`
- `DecodedBandView`
- `SourceArtifact`
