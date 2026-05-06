---
title: Overview
status: current spec
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

## 2. Public Interface

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

Planned missing objects:

- `SourceArtifact`

