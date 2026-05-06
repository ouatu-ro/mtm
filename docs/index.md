---
title: MTM Documentation
description: Entry point for MTM specs, runbooks, results, tools, and user guides.
status: current
audience: user
---

# MTM Documentation

Meta Turing Machine (MTM) is a compiler toolchain for Universal Turing Machines (UTMs).

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

Start here:

- [Specs](specs/spec.md)
- [Runbooks](runbooks/l2-incrementer.md)
- [Results](results/index.md)
- [Tools](tools/index.md)
- [User guide](user-guide/cli.md)

