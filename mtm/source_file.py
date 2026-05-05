"""Load plain Python TM definitions from a file."""

from __future__ import annotations

from pathlib import Path
from runpy import run_path

from .fixtures import TMFixture
from .semantic_objects import SourceArtifact, TMBand, TMInstance
from .source_encoding import L, R, TMProgram


def _read_required(namespace: dict[str, object], name: str):
    if name not in namespace:
        raise KeyError(f"TM input file must define `{name}`")
    return namespace[name]


def load_python_tm(path: str | Path) -> TMFixture:
    path = Path(path)
    namespace = run_path(str(path), init_globals={"L": L, "R": R, "TMBand": TMBand, "TMProgram": TMProgram})
    tm_program = _read_required(namespace, "tm_program")
    band = _read_required(namespace, "band")
    initial_state = _read_required(namespace, "initial_state")
    halt_state = _read_required(namespace, "halt_state")
    note = namespace.get("note", f"Loaded from {path.name}.")
    if not isinstance(tm_program, TMProgram):
        raise TypeError("TM input file must define `tm_program` as a TMProgram")
    if not isinstance(band, TMBand):
        raise TypeError("TM input file must define `band` as a TMBand")
    return TMFixture(
        name=namespace.get("name", path.stem),
        tm_program=tm_program,
        band=band,
        initial_state=initial_state,
        halt_state=halt_state,
        note=note,
    )


def load_python_tm_instance(path: str | Path) -> TMInstance:
    fixture = load_python_tm(path)
    return TMInstance(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )


def source_artifact_from_python(path: str | Path) -> SourceArtifact:
    fixture = load_python_tm(path)
    return SourceArtifact(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
        name=fixture.name,
        note=fixture.note,
    )


__all__ = ["load_python_tm", "load_python_tm_instance", "source_artifact_from_python"]
