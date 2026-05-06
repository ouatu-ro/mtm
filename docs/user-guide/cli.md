---
title: CLI Guide
description: Quick guide to the MTM command line and its main workflows.
status: current
audience: user
---

# CLI Guide

`mtm` is the top-level command for compiling, emitting, running, tracing, and
debugging MTM artifacts.

The parser help is the authoritative flag reference. Use `mtm COMMAND -h` for
exact inputs, outputs, and examples.

## Common commands

- `mtm compile` compiles a Python TM file into a `.utm.band` artifact.
- `mtm emit-asm` emits width-specialized Meta-ASM.
- `mtm emit-tm` emits a lowered raw UTM `.tm`.
- `mtm emit-source` writes a safe `.mtm.source` artifact.
- `mtm l1` emits source, L1 `.utm.band`, and L1 `.tm` artifacts.
- `mtm l2` emits L2 artifacts from L1 `.tm` and L1 `.utm.band`.
- `mtm run` runs a `.tm` program on a `.utm.band` input.
- `mtm trace` emits a TSV trace for a `.tm` and `.utm.band` pair.
- `mtm dbg` starts the debugger REPL.

## Common workflows

```text
mtm l1 examples/incrementer_tm.py --out-dir out
mtm l2 out/incrementer_tm.l1.tm out/incrementer_tm.l1.utm.band --out-dir out
mtm run out/incrementer_tm.l1.tm out/incrementer_tm.l1.utm.band
mtm trace out/incrementer_tm.l1.tm out/incrementer_tm.l1.utm.band --level raw --out out/raw.tsv
mtm dbg out/incrementer_tm.l1.tm out/incrementer_tm.l1.utm.band
```

## Related docs

- [MTM Specs](../specs/spec.md)
- [L2 Incrementer Runbook](../runbooks/l2-incrementer.md)
- [Debugger REPL Spec](../specs/debugger-repl.md)
- [Help Menu RFC](../rfc/help-menu.md)

