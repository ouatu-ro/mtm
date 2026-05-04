"""Bit-level encoding for source Turing machines."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log2
from typing import Iterable

L, R = -1, 1

TMProgram = dict[tuple[str, str], tuple[str, str, int]]


@dataclass(frozen=True)
class TMAbi:
    """Target encoding family / machine family."""

    state_width: int
    symbol_width: int
    dir_width: int
    grammar_version: str = "mtm-v1"
    family_label: str = ""


AbiRequirement = TMAbi


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


def collect_alphabet(
    tm_program: TMProgram,
    *,
    halt_state: str,
    blank: str,
    initial_state: str | None = None,
    source_symbols: Iterable[str] = (),
) -> tuple[list[str], list[str]]:
    states, symbols = {halt_state}, {blank}
    for (state, read_symbol), (next_state, write_symbol, _move_direction) in tm_program.items():
        states.update((state, next_state))
        symbols.update((read_symbol, write_symbol))
    if initial_state is not None:
        states.add(initial_state)
    symbols.update(source_symbols)
    return sorted(states), sorted(symbols)


def infer_minimal_abi(
    tm_program: TMProgram,
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    source_symbols: Iterable[str] = (),
) -> TMAbi:
    states, symbols = collect_alphabet(
        tm_program,
        halt_state=halt_state,
        blank=blank,
        initial_state=initial_state,
        source_symbols=source_symbols,
    )
    state_width = width_for(len(states))
    symbol_width = width_for(len(symbols))
    dir_width = width_for(2)
    return TMAbi(
        state_width=state_width,
        symbol_width=symbol_width,
        dir_width=dir_width,
        family_label=f"min[Wq={state_width},Ws={symbol_width},Wd={dir_width}]",
    )


def build_encoding(
    tm_program: TMProgram,
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    source_symbols: Iterable[str] = (),
    abi: TMAbi | None = None,
) -> Encoding:
    states, symbols = collect_alphabet(
        tm_program,
        halt_state=halt_state,
        blank=blank,
        initial_state=initial_state,
        source_symbols=source_symbols,
    )
    direction_ids = {L: 0, R: 1}
    required_state_width = width_for(len(states))
    required_symbol_width = width_for(len(symbols))
    required_dir_width = width_for(len(direction_ids))
    if abi is None:
        state_width, symbol_width, direction_width = required_state_width, required_symbol_width, required_dir_width
    else:
        errors = []
        if required_state_width > abi.state_width:
            errors.append(f"states require {required_state_width} bits, ABI provides {abi.state_width}")
        if required_symbol_width > abi.symbol_width:
            errors.append(f"symbols require {required_symbol_width} bits, ABI provides {abi.symbol_width}")
        if required_dir_width > abi.dir_width:
            errors.append(f"directions require {required_dir_width} bits, ABI provides {abi.dir_width}")
        if errors:
            raise ValueError("selected ABI too small: " + "; ".join(errors))
        state_width, symbol_width, direction_width = abi.state_width, abi.symbol_width, abi.dir_width
    return Encoding(
        state_ids=assign_ids(states),
        symbol_ids=assign_ids(symbols),
        direction_ids=direction_ids,
        state_width=state_width,
        symbol_width=symbol_width,
        direction_width=direction_width,
        blank=blank,
        initial_state=initial_state,
        halt_state=halt_state,
    )


def encode_state(encoding: Encoding, state: str) -> tuple[str, ...]: return bits(encoding.state_ids[state], encoding.state_width)
def encode_symbol(encoding: Encoding, symbol: str) -> tuple[str, ...]: return bits(encoding.symbol_ids[symbol], encoding.symbol_width)
def encode_direction(encoding: Encoding, direction: int) -> tuple[str, ...]: return bits(encoding.direction_ids[direction], encoding.direction_width)


__all__ = [
    "AbiRequirement",
    "Encoding",
    "L",
    "R",
    "TMAbi",
    "TMProgram",
    "assign_ids",
    "bits",
    "build_encoding",
    "collect_alphabet",
    "encode_direction",
    "encode_state",
    "encode_symbol",
    "infer_minimal_abi",
    "unbits",
    "width_for",
]
