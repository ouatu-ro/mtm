"""Sample Turing machine fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pkgutil import iter_modules

from ..utm_band_layout import EncodedTape, compile_tm_to_universal_tape
from ..source_encoding import TMAbi, TMProgram
from ..semantic_objects import SourceTape

@dataclass(frozen=True)
class TMFixture:
    """A runnable TM program plus its source-level input tape."""

    name: str; tm_program: TMProgram; tape: SourceTape
    initial_state: str; halt_state: str; note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.tm_program, TMProgram):
            raise TypeError("TMFixture.tm_program must be a TMProgram")
        if not isinstance(self.tape, SourceTape):
            raise TypeError("TMFixture.tape must be a SourceTape")

    def build_tape(self, *, abi: TMAbi | None = None) -> EncodedTape:
        return compile_tm_to_universal_tape(
            self.tm_program,
            self.tape,
            initial_state=self.initial_state,
            halt_state=self.halt_state,
            abi=abi,
        )

    def describe(self) -> str:
        from ..pretty import pretty_fixture
        return pretty_fixture(self)


def format_tm_program(tm_program: TMProgram) -> str:
    rows = []
    for (state, read_symbol), (next_state, write_symbol, move_direction) in tm_program.items():
        rows.append(f"  {state!r}, {read_symbol!r} -> {next_state!r}, {write_symbol!r}, {move_direction}")
    return "\n".join(rows)


def _load_fixture_module(name: str): return import_module(f".{name}", __name__)


def list_fixtures() -> list[str]:
    return sorted(name for _, name, is_package in iter_modules(__path__) if not is_package and not name.startswith("_"))


def load_fixture(name: str) -> TMFixture:
    module = _load_fixture_module(name)
    fixture = getattr(module, "fixture", None)
    if fixture is None:
        raise AttributeError(f"fixture module {name!r} must define `fixture = TMFixture(...)`")
    if not isinstance(fixture, TMFixture):
        raise TypeError(f"fixture module {name!r} exported {type(fixture).__name__}, expected TMFixture")
    return fixture


__all__ = ["TMFixture", "format_tm_program", "list_fixtures", "load_fixture"]
