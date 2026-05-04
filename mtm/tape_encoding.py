"""Bit-level encoding for source Turing machines."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log2
from typing import Iterable

L, R = -1, 1

TMProgram = dict[tuple[str, str], tuple[str, str, int]]


def width_for(count: int) -> int: return 1 if count <= 1 else ceil(log2(count))
def assign_ids(values: Iterable[str | int]) -> dict[str | int, int]: return {value: index for index, value in enumerate(values)}


def bits(value: int, width: int) -> tuple[str, ...]:
    if not 0 <= value < (1 << width):
        raise ValueError(f"value {value} does not fit in {width} bits")
    return tuple("1" if (value >> index) & 1 else "0" for index in reversed(range(width)))


def unbits(bit_values: Iterable[str]) -> int:
    value = 0
    for bit in bit_values:
        if bit not in {"0", "1"}:
            raise ValueError(f"not a bit: {bit!r}")
        value = (value << 1) | (bit == "1")
    return value


@dataclass(frozen=True)
class Encoding:
    """Dense bit encoding for source TM states, symbols, and directions."""

    state_ids: dict[str, int]; symbol_ids: dict[str, int]; direction_ids: dict[int, int]
    state_width: int; symbol_width: int; direction_width: int
    blank: str; initial_state: str; halt_state: str

    @property
    def id_states(self) -> dict[int, str]: return {value: key for key, value in self.state_ids.items()}

    @property
    def id_symbols(self) -> dict[int, str]: return {value: key for key, value in self.symbol_ids.items()}

    @property
    def id_dirs(self) -> dict[int, int]: return {value: key for key, value in self.direction_ids.items()}


def collect_alphabet(tm_program: TMProgram, *, halt_state: str, blank: str) -> tuple[list[str], list[str]]:
    states, symbols = {halt_state}, {blank}
    for (state, read_symbol), (next_state, write_symbol, _move_direction) in tm_program.items():
        states.update((state, next_state))
        symbols.update((read_symbol, write_symbol))
    return sorted(states), sorted(symbols)


def build_encoding(
    tm_program: TMProgram,
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
) -> Encoding:
    states, symbols = collect_alphabet(tm_program, halt_state=halt_state, blank=blank)
    if initial_state not in states:
        states = sorted(states + [initial_state])
    return Encoding(
        state_ids=assign_ids(states),
        symbol_ids=assign_ids(symbols),
        direction_ids={L: 0, R: 1},
        state_width=width_for(len(states)),
        symbol_width=width_for(len(symbols)),
        direction_width=1,
        blank=blank,
        initial_state=initial_state,
        halt_state=halt_state,
    )


def encode_state(encoding: Encoding, state: str) -> tuple[str, ...]: return bits(encoding.state_ids[state], encoding.state_width)
def encode_symbol(encoding: Encoding, symbol: str) -> tuple[str, ...]: return bits(encoding.symbol_ids[symbol], encoding.symbol_width)
def encode_direction(encoding: Encoding, direction: int) -> tuple[str, ...]: return bits(encoding.direction_ids[direction], encoding.direction_width)


__all__ = [
    "Encoding",
    "L",
    "R",
    "TMProgram",
    "assign_ids",
    "bits",
    "build_encoding",
    "collect_alphabet",
    "encode_direction",
    "encode_state",
    "encode_symbol",
    "unbits",
    "width_for",
]
