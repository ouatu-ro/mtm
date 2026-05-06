---
title: Debugger Guide
description: Practical entry point for the MTM debugger REPL and trace tools.
audience: user
---

# Debugger Guide

`mtm dbg` starts an interactive REPL over either a built-in fixture or an
explicit `.tm` / `.utm.band` pair.

The raw TM trace is the executable truth. Higher-level views are derived from
the trace, the source map, and the debugger presentation model.

## Built-In Fixtures

Fixture modules live in `mtm/fixtures/`.

Current fixtures:

- `incrementer`
- `palindrome`

Start a fixture session:

```sh
uv run mtm dbg incrementer
uv run mtm dbg palindrome
```

The explicit fixture flag is equivalent:

```sh
uv run mtm dbg --fixture incrementer
```

## Debug Artifacts

First compile a source example:

```sh
mkdir -p out
uv run mtm compile examples/incrementer_tm.py \
  -o out/incrementer.utm.band \
  --tm-out out/incrementer.tm
```

Then open the artifact pair:

```sh
uv run mtm dbg out/incrementer.tm out/incrementer.utm.band
```

Use `--max-raw` when grouped stepping needs more raw transition budget:

```sh
uv run mtm dbg out/incrementer.tm out/incrementer.utm.band --max-raw 1000000
```

## Core Commands

Inspection:

- `status`
- `view`
- `where`
- `help`

Forward stepping:

- `step raw`
- `step routine`
- `step instruction`
- `step block`
- `step source`

Backward stepping:

- `back raw`
- `back routine`
- `back instruction`
- `back block`
- `back source`

Configuration and exit:

- `set max-raw N`
- `quit`

Shortcuts are available for the same boundary levels. The detailed behavior is
documented in [Debugger REPL Spec](../specs/debugger-repl.md).

## Boundary Levels

- `raw`: one raw TM transition
- `routine`: one lowered helper routine span
- `instruction`: one Meta-ASM instruction boundary
- `block`: one Meta-ASM block boundary
- `source`: one simulated guest/source TM transition

`source` means one simulated source-TM transition, not one Python source line.

## Trace Files

For offline inspection, use `mtm trace`:

```sh
uv run mtm trace out/incrementer.tm out/incrementer.utm.band \
  --level raw \
  --max-steps 500 \
  --out out/incrementer.raw.tsv \
  --meta-out out/incrementer.raw.json
```

The browser trace viewer can load the TSV plus JSON sidecar. See
[Trace Viewer](../tools/trace-viewer.md).

## Related Docs

- [CLI Guide](cli.md)
- [Debugger REPL Spec](../specs/debugger-repl.md)
- [Debugger Stepper Layers](../architecture/debugger-stepper.md)
