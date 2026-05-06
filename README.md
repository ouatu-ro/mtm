# MTM

Meta Turing Machine (MTM) is a compiler toolchain for building and inspecting
Universal Turing Machines.

MTM has working pieces for:

- a small Meta-ASM language for generating a UTM
- a universal interpreter over encoded TM bands
- multi-pass lowering from Meta-ASM into raw TM transitions
- recursive bootstrapping experiments, including C-accelerated runners
- debugging and trace tools: `mtm dbg`, `mtm trace`, and the browser trace viewer

## Install

Install `uv`, then sync and run from the repo:

```sh
uv sync
uv run mtm -h
```

## Quick Start

Compile the incrementer example into an encoded band plus a runnable raw UTM:

```sh
mkdir -p out
uv run mtm compile examples/incrementer_tm.py \
  -o out/incrementer.utm.band \
  --tm-out out/incrementer.tm \
  --asm-out out/incrementer.asm
```

Run it:

```sh
uv run mtm run out/incrementer.tm out/incrementer.utm.band
```

Emit a raw trace and metadata sidecar:

```sh
uv run mtm trace out/incrementer.tm out/incrementer.utm.band \
  --level raw \
  --max-steps 500 \
  --out out/incrementer.raw.tsv \
  --meta-out out/incrementer.raw.json
```

Debug a built-in fixture:

```sh
uv run mtm dbg incrementer
```

Built-in fixtures live in `mtm/fixtures/`; source examples live in `examples/`.

## Inputs

Normal compilation starts from Python TM files such as
`examples/incrementer_tm.py`. Raw `.tm` programs can also become guests in the
advanced recursive path, where an existing `.tm` and `.utm.band` pair is wrapped
into a higher-level encoded band.

The L2/bootstrap path is experimental and documented separately:
[docs/runbooks/l2-incrementer.md](docs/runbooks/l2-incrementer.md).

Docs start here: [docs/index.md](docs/index.md).
