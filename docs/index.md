---
title: MTM Documentation
description: Entry point for MTM specs, architecture, runbooks, results, tools, and user guides.
audience: user
---

# MTM Documentation

Meta Turing Machine (MTM) is a compiler toolchain for Universal Turing Machines (UTMs).

MTM uses a fixed-width ABI for the encoded guest machine:

```text
band_abi = (
  state_width,
  symbol_width,
  dir_width,
  grammar_version
)
```

An encoded TM runs on a host UTM only when the guest ABI fits the host ABI.

MTM is organized as a staged compiler and execution pipeline:

```text
Source guest layer
  TMProgram + TMBand + initial_state + halt_state
    -> TMInstance

ABI and encoding layer
  TMInstance
    -> TMAbi
    -> Encoding

Source guest compiler
  TMInstance
    -> UTMEncoded

Encoded UTM band
  UTMEncoded
    -> UTMBandArtifact

Universal interpreter generator
  Encoding
    -> UniversalInterpreter
    -> MetaASMProgram

Meta-ASM lowering pipeline
  MetaASMProgram
    -> Routine
    -> RoutineCFG
    -> TMBuilder
    -> TMTransitionProgram

Raw execution layer
  UTMProgramArtifact + UTMBandArtifact
    -> RawTMInstance

Debugger and trace layer
  TMTransitionProgram + runtime tape + TransitionSourceMap
    -> RawTraceRunner
    -> TraceFacts
    -> DebuggerQueries
```

The same staged structure is described in more detail in the spec pages.

Start here:

- [Specs](specs/spec.md)
- [Overview](specs/overview.md)
- [Runbooks](runbooks/l2-incrementer.md)
- [Results](results/index.md)
- [Tools](tools/index.md)
- [User guide](user-guide/cli.md)
