"""Sample Turing machine fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pkgutil import iter_modules

from ..utm_band_layout import EncodedBand, compile_tm_to_universal_tape
from ..source_encoding import TMAbi, TMProgram
from ..semantic_objects import TMBand

@dataclass(frozen=True)
class TMFixture:
    """A runnable TM program plus its source-level input band."""

    name: str; tm_program: TMProgram; band: TMBand
    initial_state: str; halt_state: str; note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.tm_program, TMProgram):
            raise TypeError("TMFixture.tm_program must be a TMProgram")
        if not isinstance(self.band, TMBand):
            raise TypeError("TMFixture.band must be a TMBand")

    def build_band(self, *, abi: TMAbi | None = None) -> EncodedBand:
        return compile_tm_to_universal_tape(
            self.tm_program,
            self.band,
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


def load_fixture_module(name: str): return import_module(f".{name}", __name__)


def list_fixtures() -> list[str]:
    return sorted(name for _, name, is_package in iter_modules(__path__) if not is_package and not name.startswith("_"))


def get_fixture(name: str) -> TMFixture: return load_fixture(name)


def load_fixture(name: str) -> TMFixture:
    module = load_fixture_module(name)
    fixture = getattr(module, "fixture", None)
    if fixture is None:
        raise AttributeError(f"fixture module {name!r} must define `fixture = TMFixture(...)`")
    if not isinstance(fixture, TMFixture):
        raise TypeError(f"fixture module {name!r} exported {type(fixture).__name__}, expected TMFixture")
    return fixture


__all__ = ["TMFixture", "format_tm_program", "get_fixture", "list_fixtures", "load_fixture", "load_fixture_module"]
