# MTM

Meta Turing Machine (MTM) is a compiler toolchain for building, running, and
inspecting Universal Turing Machines (UTMs).

The project takes a source Turing machine, encodes it onto a UTM tape, generates
a universal interpreter for that encoding, lowers the interpreter into ordinary
TM transitions, and then lets you run, trace, and debug the result.

Current highlights:

- Meta-ASM: a small assembly language for generating a UTM
- a universal interpreter over encoded TM tapes, stored as `.utm.band` artifacts
- multi-pass lowering from Meta-ASM into raw `.tm` transition tables
- recursive bootstrapping experiments, including C-accelerated runners
- debugging and trace tools: `mtm dbg`, `mtm trace`, and the browser trace viewer

## Install

Install `uv`, then sync the project and check the CLI:

```sh
uv sync
uv run mtm -h
```

## Quick Start

Compile the incrementer example into:

- `out/incrementer.utm.band`: encoded input tape for the UTM
- `out/incrementer.tm`: runnable raw UTM transition table
- `out/incrementer.asm`: generated Meta-ASM, for inspection

```sh
mkdir -p out
uv run mtm compile examples/source/incrementer_tm.py \
  -o out/incrementer.utm.band \
  --tm-out out/incrementer.tm \
  --asm-out out/incrementer.asm
```

Run the raw UTM on the encoded tape:

```sh
uv run mtm run out/incrementer.tm out/incrementer.utm.band
```

Emit a raw transition trace plus metadata sidecar:

```sh
uv run mtm trace out/incrementer.tm out/incrementer.utm.band \
  --level raw \
  --max-steps 500 \
  --out out/incrementer.raw.tsv \
  --meta-out out/incrementer.raw.json
```

Inspect traces in the browser viewer:

```sh
open tools/trace-viewer.html
```

Open the debugger on a built-in fixture:

```sh
uv run mtm dbg incrementer
```

## Inputs

Normal compilation starts from Python TM source files, such as:

- `examples/source/incrementer_tm.py`
- `examples/source/palindrome_tm.py`
- `examples/source/right_left_walk_tm.py`

Those files are plain Python modules. The loader injects `SourceTape`,
`TMProgram`, `L`, and `R`; the module must define `tape`, `tm_program`,
`initial_state`, and `halt_state`. `name` and `note` are optional.

```python
blank = "_"
initial_state = "q0"
halt_state = "qH"

tape = SourceTape(right_band=("1", "0", "_"), head=0, blank=blank)

tm_program = TMProgram({
    ("q0", "1"): ("qH", "0", R),
}, initial_state=initial_state, halt_state=halt_state, blank=blank)
```

Raw transition examples live under `examples/`; the trace-viewer fixture bundle
lives with the viewer:

- `examples/raw/right-left-walk.tm`
- `tools/trace-viewer-assets/fixtures.js`: bundled fixture data for `tools/trace-viewer.html`

The trace viewer can also load your own `mtm trace --out ... --meta-out ...`
files through the file pickers.

Built-in debugger fixtures live in `mtm/fixtures/` and currently include:

- `incrementer`
- `palindrome`

Raw `.tm` programs can also become guests in the advanced recursive path. In
that path, an existing `.tm` plus `.utm.band` pair is wrapped into a higher-level
encoded tape. This is the experimental L2/bootstrap workflow, not the normal
compile/run path.

See [docs/runbooks/l2-incrementer.md](docs/runbooks/l2-incrementer.md) for the
bootstrap notes.

## Documentation

Start at [docs/index.md](docs/index.md).

## Primary background:

- Alan M. Turing, “On Computable Numbers, with an Application to the
  Entscheidungsproblem”, 1936/1937.
  https://www.cs.virginia.edu/~robins/Turing_Paper_1936.pdf
