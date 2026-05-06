# MTM

Meta Turing Machine (MTM) is a compiler toolchain for Universal Turing
Machines.

```text
source TM instance
  -> encoded UTM band
  -> generated universal interpreter
  -> raw TM execution
```

Common entrypoints:

```text
uv run mtm -h
uv run mtm compile -h
uv run mtm dbg -h
```

Docs start here: [docs/index.md](docs/index.md)
