# RFC: MTM Help Menu

## Motivation

MTM has two kinds of help:

- CLI help for artifact workflows such as `compile`, `l1`, `l2`, `trace`, and
  `dbg`
- debugger REPL help for interactive commands such as `step`, `back`, `where`,
  and `view`

The CLI help should be the authoritative flag reference because it is generated
from the parser that actually accepts the commands. A separate usage document
can still be useful, but it should be a guided quickstart rather than a second
complete option reference.

## Current Direction

Keep global CLI help in argparse and improve it with:

- explicit file-shaped metavars such as `INPUT.py`, `HOST.tm`, and
  `INPUT.utm.band`
- short option descriptions
- command-specific examples
- a top-level workflow overview
- plain terminal output that copies cleanly into docs, issues, and CI logs

The debugger REPL keeps its own structured `help` command because it is a
different command language inside an interactive session.

## Proposed Future Shape

Top-level `mtm -h` should answer:

- what commands exist
- which commands belong to the common L1/L2 workflow
- how to discover command-specific flags

Subcommand help, `mtm COMMAND -h`, should answer:

- required inputs and outputs
- file formats expected by the command
- important safety/fuel controls
- one or two realistic examples

A future `Usage.md` should be a recipe document:

- compile and run the incrementer
- emit L1 artifacts
- emit L2 artifacts
- emit traces at raw/instruction/block/source levels
- debug a fixture or artifact pair

It should defer exact flag reference to `mtm COMMAND -h`.

## Rich / Color

Rich output is useful for `mtm dbg`, where the UI is interactive and already has
presentation objects. Global `--help` should stay plain for now.

If color is added later, it should:

- gracefully fall back to plain text
- only colorize when stdout is a TTY
- respect `NO_COLOR`
- avoid making argparse depend on Rich-specific semantics

## Non-Goals

- No separate exhaustive CLI reference that can drift from argparse.
- No required Rich dependency for normal `mtm -h`.
- No generated docs pipeline until the command surface stabilizes further.
