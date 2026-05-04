"""Load plain Python TM definitions from a file."""

from __future__ import annotations

from pathlib import Path
from runpy import run_path

from .fixtures import TMFixture
from .semantic_objects import TMBand, TMInstance
from .tape_encoding import L, R


def _read_required(namespace: dict[str, object], name: str):
    if name not in namespace:
        raise KeyError(f"TM input file must define `{name}`")
    return namespace[name]


def load_python_tm(path: str | Path) -> TMFixture:
    path = Path(path)
    namespace = run_path(str(path), init_globals={"L": L, "R": R})
    tm_program = _read_required(namespace, "tm_program")
    initial_state = _read_required(namespace, "initial_state")
    halt_state = _read_required(namespace, "halt_state")
    blank = namespace.get("blank", "_")
    input_symbols = namespace.get("input_symbols", list(namespace.get("input_string", "")))
    if isinstance(input_symbols, str):
        input_symbols = list(input_symbols)
    blanks_left = namespace.get("blanks_left", 0)
    blanks_right = namespace.get("blanks_right", 8)
    note = namespace.get("note", f"Loaded from {path.name}.")
    return TMFixture(
        name=namespace.get("name", path.stem),
        tm_program=tm_program,
        input_symbols=list(input_symbols),
        initial_state=initial_state,
        halt_state=halt_state,
        blank=blank,
        blanks_left=blanks_left,
        blanks_right=blanks_right,
        note=note,
    )


def load_python_tm_instance(path: str | Path) -> TMInstance:
    fixture = load_python_tm(path)
    cells = tuple([fixture.blank] * fixture.blanks_left + fixture.input_symbols + [fixture.blank] * fixture.blanks_right)
    return TMInstance(
        program=fixture.tm_program,
        band=TMBand(cells=cells, head=fixture.blanks_left, blank=fixture.blank),
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )


__all__ = ["load_python_tm", "load_python_tm_instance"]
