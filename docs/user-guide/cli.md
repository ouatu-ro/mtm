---
title: CLI Guide
description: Practical guide to normal MTM command-line workflows.
audience: user
---

# CLI Guide

`mtm` compiles source Turing machines into UTM artifacts, runs those artifacts,
and emits traces for inspection.

Use `uv run mtm COMMAND -h` for the exact flag reference. This guide focuses on
the normal workflows.

## Install

From the repository root:

```sh
uv sync
uv run mtm -h
```

## Inputs

Normal source inputs are Python TM files. Existing examples:

- `examples/incrementer_tm.py`
- `examples/palindrome_tm.py`
- `examples/demo.py`

Built-in debugger fixtures live in `mtm/fixtures/`:

- `incrementer`
- `palindrome`

Artifact inputs are:

- `.utm.band`: encoded UTM input band
- `.tm`: lowered raw TM transition table
- `.asm`: emitted Meta-ASM, for inspection
- `.mtm.source`: safe serialized source artifact

Raw `.tm` programs can also be compiled as guests in the advanced recursive
path. That is the L2/bootstrap workflow, not the default day-to-day path.

## Compile A Python TM

Compile a Python source TM into an encoded band:

```sh
mkdir -p out
uv run mtm compile examples/incrementer_tm.py \
  -o out/incrementer.utm.band
```

Compile and also emit the runnable raw UTM plus Meta-ASM:

```sh
uv run mtm compile examples/incrementer_tm.py \
  -o out/incrementer.utm.band \
  --tm-out out/incrementer.tm \
  --asm-out out/incrementer.asm
```

The equivalent split commands are:

```sh
uv run mtm emit-asm examples/incrementer_tm.py -o out/incrementer.asm
uv run mtm emit-tm examples/incrementer_tm.py -o out/incrementer.tm
uv run mtm emit-source examples/incrementer_tm.py -o out/incrementer.mtm.source
```

## Run

Run a lowered `.tm` host on an encoded `.utm.band` input:

```sh
uv run mtm run out/incrementer.tm out/incrementer.utm.band
```

Use more fuel for larger runs:

```sh
uv run mtm run out/incrementer.tm out/incrementer.utm.band --max-steps 1000000
```

## Trace

Emit raw transitions:

```sh
uv run mtm trace out/incrementer.tm out/incrementer.utm.band \
  --level raw \
  --max-steps 500 \
  --out out/incrementer.raw.tsv \
  --meta-out out/incrementer.raw.json
```

Emit grouped instruction or block traces:

```sh
uv run mtm trace out/incrementer.tm out/incrementer.utm.band \
  --level instruction \
  --max-steps 100 \
  --out out/incrementer.instruction.tsv

uv run mtm trace out/incrementer.tm out/incrementer.utm.band \
  --level block \
  --max-steps 100 \
  --out out/incrementer.block.tsv
```

The trace viewer is documented in [Trace Viewer](../tools/trace-viewer.md).

## Debug

Start from a built-in fixture:

```sh
uv run mtm dbg incrementer
uv run mtm dbg palindrome
```

Debug an explicit artifact pair:

```sh
uv run mtm dbg out/incrementer.tm out/incrementer.utm.band
```

See [Debugger Guide](debugger.md) for REPL commands and stepping levels.

## Advanced Bootstrapping

`mtm l1` and `mtm l2` are for recursive/bootstrap experiments.

`mtm l1` emits the source artifact, L1 band, and L1 host in one bundle:

```sh
uv run mtm l1 examples/incrementer_tm.py --out-dir out --stem incrementer
```

`mtm l2` wraps an existing L1 `.tm` plus `.utm.band` as a raw guest:

```sh
uv run mtm l2 out/incrementer.l1.tm out/incrementer.l1.utm.band --out-dir out
```

That path is expensive and experimental. The detailed bootstrap notes live in
[L2 Incrementer Runbook](../runbooks/l2-incrementer.md) and
[L2 Bootstrap Results](../results/l2-bootstrap.md).

## Related Docs

- [MTM Specs](../specs/spec.md)
- [Debugger Guide](debugger.md)
- [Tools](../tools/index.md)
