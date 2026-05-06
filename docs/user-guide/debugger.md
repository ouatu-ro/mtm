---
title: Debugger Guide
description: Practical entry point for the MTM debugger REPL.
status: current
audience: user
---

# Debugger Guide

`mtm dbg` starts the in-process debugger REPL over either a built-in fixture or
an explicit `HOST.tm` and `INPUT.utm.band` pair.

The raw TM trace is the executable truth. Higher-level views are derived from
the trace, the source map, and the debugger presentation model.

## Start points

```text
mtm dbg incrementer
mtm dbg --fixture incrementer
mtm dbg utm.tm input.utm.band
```

## Commands

The main commands are:

- `status`
- `view`
- `where`
- `step raw`
- `step routine`
- `step instruction`
- `step block`
- `step source`
- `back raw`
- `back routine`
- `back instruction`
- `back block`
- `back source`
- `set max-raw N`
- `help`
- `quit`

Shortcuts are available for the same boundary levels. The spec documents the
full shortcut set and stepping rules.

## Boundary levels

The debugger steps at these boundaries:

- `raw`
- `routine`
- `instruction`
- `block`
- `source`

`source` means one simulated source-TM transition, not one Python source line.

## Related docs

- [Debugger REPL Spec](../specs/debugger-repl.md)
- [Debugger Presentation Model Spec](../specs/debugger-presentation.md)
- [Debugger Stepper Layers](../architecture/debugger-stepper.md)

