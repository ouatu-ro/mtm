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

- `examples/source/incrementer_tm.py`
- `examples/source/palindrome_tm.py`
- `examples/demo.py`

Built-in debugger fixtures live in `mtm/fixtures/`:

- `incrementer`
- `palindrome`

Artifact inputs are:

- `.utm.band`: encoded guest tape artifact
- `.tm`: lowered raw TM transition table
- `.asm`: emitted Meta-ASM, for inspection
- `.mtm.source`: safe serialized source artifact

Use `mtm inspect` to summarize generated artifacts, and `mtm concepts` for the
short vocabulary behind object names such as `SourceTape`, `EncodedTape`, and
`UTMBandArtifact`.

Raw `.tm` programs can also be compiled as guests in the advanced recursive
path. That is the L2/bootstrap workflow, not the default day-to-day path.

## Compile A Python TM

Compile a Python source TM into an encoded guest tape:

```sh
mkdir -p out
uv run mtm compile examples/source/incrementer_tm.py \
  -o out/incrementer.utm.band
```

Compile and also emit the runnable raw UTM plus Meta-ASM:

```sh
uv run mtm compile examples/source/incrementer_tm.py \
  -o out/incrementer.utm.band \
  --tm-out out/incrementer.tm \
  --asm-out out/incrementer.asm
```

The equivalent split commands are:

```sh
uv run mtm emit-asm examples/source/incrementer_tm.py -o out/incrementer.asm
uv run mtm emit-tm examples/source/incrementer_tm.py -o out/incrementer.tm
uv run mtm emit-source examples/source/incrementer_tm.py -o out/incrementer.mtm.source
```

## Inspect

Summarize generated artifacts without running them:

```sh
uv run mtm inspect out/incrementer.utm.band
uv run mtm inspect out/incrementer.tm out/incrementer.mtm.source
```

Print the vocabulary used by the CLI and docs:

```sh
uv run mtm concepts
uv run mtm concepts UTMBandArtifact
```

The vocabulary source lives in [Concepts](../reference/concepts.md).

## Run

Run a lowered `.tm` host on an encoded `.utm.band` input:

```sh
uv run mtm run out/incrementer.tm out/incrementer.utm.band
```

Use more fuel for larger runs:

```sh
uv run mtm run out/incrementer.tm out/incrementer.utm.band --max-steps 1000000
```

Choose the output view explicitly when you want to inspect a specific layer:

```sh
uv run mtm run out/incrementer.tm out/incrementer.utm.band --view decoded
uv run mtm run out/incrementer.tm out/incrementer.utm.band --view encoded --when final
uv run mtm run out/incrementer.tm out/incrementer.utm.band --view raw --around-head 80

uv run mtm run out/incrementer.tm out/incrementer.utm.band --view raw --range -200:120
uv run mtm run out/incrementer.tm out/incrementer.utm.band --view encoded --side right
```

`decoded` shows the simulated guest tape and registers. `encoded` shows the
concrete split UTM tape layout. `raw` shows the actual sparse runtime tape used
by the lowered raw TM runner.

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
uv run mtm l1 examples/source/incrementer_tm.py --out-dir out --stem incrementer
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
- [Concepts](../reference/concepts.md)
- [Debugger Guide](debugger.md)
- [Tools](../tools/index.md)
