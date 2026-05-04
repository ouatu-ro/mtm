"""Sample Turing machine fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pkgutil import iter_modules

from ..compiled_band import EncodedBand, compile_tm_to_universal_tape
from ..tape_encoding import TMProgram

@dataclass(frozen=True)
class TMFixture:
    """A runnable TM program plus the input and tape margins it needs."""

    name: str; tm_program: TMProgram; input_symbols: list[str]
    initial_state: str; halt_state: str; blank: str = "_"
    blanks_left: int = 0; blanks_right: int = 8; note: str = ""

    def build_band(self) -> EncodedBand:
        return compile_tm_to_universal_tape(
            self.tm_program,
            self.input_symbols,
            initial_state=self.initial_state,
            halt_state=self.halt_state,
            blank=self.blank,
            blanks_left=self.blanks_left,
            blanks_right=self.blanks_right,
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


__all__ = [
    "TMFixture",
    "format_tm_program",
    "get_fixture",
    "list_fixtures",
    "load_fixture",
    "load_fixture_module",
]
