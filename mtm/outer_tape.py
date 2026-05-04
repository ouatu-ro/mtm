"""Build the encoded outer tape for a source Turing machine."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import ceil, log2
from typing import Iterable

L, R = -1, 1

REGS, END_REGS, RULES, RULE, END_RULE, END_RULES = "#REGS", "#END_REGS", "#RULES", "#RULE", "#END_RULE", "#END_RULES"
TAPE, END_TAPE, CELL = "#TAPE", "#END_TAPE", "#CELL"
END_FIELD, END_CELL = "#END_FIELD", "#END_CELL"

CUR_STATE, CUR_SYMBOL, WRITE_SYMBOL, NEXT_STATE = "#CUR_STATE", "#CUR_SYMBOL", "#WRITE_SYMBOL", "#NEXT_STATE"
MOVE_DIR, CMP_FLAG, TMP = "#MOVE_DIR", "#CMP_FLAG", "#TMP"
STATE, READ, WRITE, NEXT, MOVE = "#STATE", "#READ", "#WRITE", "#NEXT", "#MOVE"
HEAD, NO_HEAD = "#HEAD", "#NO_HEAD"
OUTER_BLANK = "_OUTER_BLANK"

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
        direction_width=1, blank=blank, initial_state=initial_state, halt_state=halt_state,
    )


def encode_state(encoding: Encoding, state: str) -> tuple[str, ...]: return bits(encoding.state_ids[state], encoding.state_width)
def encode_symbol(encoding: Encoding, symbol: str) -> tuple[str, ...]: return bits(encoding.symbol_ids[symbol], encoding.symbol_width)
def encode_direction(encoding: Encoding, direction: int) -> tuple[str, ...]: return bits(encoding.direction_ids[direction], encoding.direction_width)


@dataclass(frozen=True)
class EncodedBand:
    """Concrete encoded outer band, split into left and right sections."""

    encoding: Encoding; outer_tape: dict[int, str]; left_band: list[str]; right_band: list[str]

    def linear(self) -> list[str]: return self.left_band + self.right_band
    def view(self) -> str: return " ".join(self.left_band + ["|"] + self.right_band)


def wrap_field(marker: str, payload: Iterable[str]) -> list[str]: return [marker, *payload, END_FIELD]


def build_register_band(encoding: Encoding) -> list[str]:
    temp_width = max(encoding.state_width, encoding.symbol_width, encoding.direction_width)
    return [
        REGS,
        *wrap_field(CUR_STATE, encode_state(encoding, encoding.initial_state)),
        *wrap_field(CUR_SYMBOL, encode_symbol(encoding, encoding.blank)),
        *wrap_field(WRITE_SYMBOL, encode_symbol(encoding, encoding.blank)),
        *wrap_field(NEXT_STATE, encode_state(encoding, encoding.initial_state)),
        *wrap_field(MOVE_DIR, encode_direction(encoding, L)),
        *wrap_field(CMP_FLAG, ("0",)),
        *wrap_field(TMP, ("0",) * temp_width),
        END_REGS,
    ]


def build_rule_band(encoding: Encoding, tm_program: TMProgram) -> list[str]:
    band = [RULES]
    for (state, read_symbol), (next_state, write_symbol, move_direction) in tm_program.items():
        band.extend([
            RULE,
            *wrap_field(STATE, encode_state(encoding, state)),
            *wrap_field(READ, encode_symbol(encoding, read_symbol)),
            *wrap_field(WRITE, encode_symbol(encoding, write_symbol)),
            *wrap_field(NEXT, encode_state(encoding, next_state)),
            *wrap_field(MOVE, encode_direction(encoding, move_direction)),
            END_RULE,
        ])
    return band + [END_RULES]


def build_tape_band(
    encoding: Encoding,
    input_symbols: Iterable[str],
    *,
    head_index: int = 0,
    blanks_left: int = 0,
    blanks_right: int = 8,
) -> list[str]:
    symbols = [encoding.blank] * blanks_left + list(input_symbols) + [encoding.blank] * blanks_right
    head_position = blanks_left + head_index
    if not 0 <= head_position < len(symbols):
        raise ValueError("head outside encoded tape band")
    band = [TAPE]
    for index, symbol in enumerate(symbols):
        band.extend([CELL, HEAD if index == head_position else NO_HEAD, *encode_symbol(encoding, symbol), END_CELL])
    return band + [END_TAPE]


def place_on_negative_side(tokens: list[str], *, start: int = -1) -> dict[int, str]: return {start - (len(tokens) - 1 - index): token for index, token in enumerate(tokens)}
def place_on_positive_side(tokens: list[str], *, start: int = 0) -> dict[int, str]: return {start + index: token for index, token in enumerate(tokens)}


def split_outer_tape(outer_tape: dict[int, str]) -> tuple[list[str], list[str]]:
    live_cells = [address for address, symbol in outer_tape.items() if symbol != OUTER_BLANK]
    if not live_cells:
        return [], []
    lowest, highest = min(live_cells), max(live_cells)
    return [outer_tape[address] for address in range(lowest, 0)], [outer_tape[address] for address in range(0, highest + 1)]


def build_outer_tape(
    tm_program: TMProgram,
    input_symbols: Iterable[str],
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    blanks_left: int = 0,
    blanks_right: int = 8,
) -> EncodedBand:
    encoding = build_encoding(tm_program, initial_state=initial_state, halt_state=halt_state, blank=blank)
    left_band = build_register_band(encoding) + build_rule_band(encoding, tm_program)
    right_band = build_tape_band(encoding, input_symbols, blanks_left=blanks_left, blanks_right=blanks_right)
    outer_tape = defaultdict(lambda: OUTER_BLANK)
    outer_tape.update(place_on_negative_side(left_band, start=-1))
    outer_tape.update(place_on_positive_side(right_band, start=0))
    return EncodedBand(encoding, outer_tape, left_band, right_band)


def compile_tm_to_universal_tape(
    tm_program: TMProgram,
    input_symbols: Iterable[str],
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    blanks_left: int = 0,
    blanks_right: int = 8,
) -> EncodedBand:
    return build_outer_tape(
        tm_program,
        input_symbols,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=blank,
        blanks_left=blanks_left,
        blanks_right=blanks_right,
    )


__all__ = [
    "CUR_STATE",
    "CUR_SYMBOL",
    "CMP_FLAG",
    "EncodedBand",
    "Encoding",
    "HEAD",
    "L",
    "MOVE_DIR",
    "NEXT_STATE",
    "NO_HEAD",
    "OUTER_BLANK",
    "R",
    "TMProgram",
    "TMP",
    "WRITE_SYMBOL",
    "bits",
    "build_encoding",
    "build_outer_tape",
    "build_register_band",
    "build_rule_band",
    "build_tape_band",
    "collect_alphabet",
    "compile_tm_to_universal_tape",
    "encode_direction",
    "encode_state",
    "encode_symbol",
    "place_on_negative_side",
    "place_on_positive_side",
    "split_outer_tape",
    "unbits",
    "width_for",
]
