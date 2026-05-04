"""Compiled outer-band layout for encoded source Turing machines."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .tape_encoding import Encoding, TMProgram, build_encoding, encode_direction, encode_state, encode_symbol, L, R

REGS, END_REGS, RULES, RULE, END_RULE, END_RULES = "#REGS", "#END_REGS", "#RULES", "#RULE", "#END_RULE", "#END_RULES"
TAPE, END_TAPE, CELL = "#TAPE", "#END_TAPE", "#CELL"
END_FIELD, END_CELL = "#END_FIELD", "#END_CELL"

CUR_STATE, CUR_SYMBOL, WRITE_SYMBOL, NEXT_STATE = "#CUR_STATE", "#CUR_SYMBOL", "#WRITE_SYMBOL", "#NEXT_STATE"
MOVE_DIR, CMP_FLAG, TMP = "#MOVE_DIR", "#CMP_FLAG", "#TMP"
STATE, READ, WRITE, NEXT, MOVE = "#STATE", "#READ", "#WRITE", "#NEXT", "#MOVE"
HEAD, NO_HEAD = "#HEAD", "#NO_HEAD"
OUTER_BLANK = "_OUTER_BLANK"


@dataclass(frozen=True)
class EncodedBand:
    """Concrete encoded band with a derived raw-tape runtime view."""

    encoding: Encoding; left_band: list[str]; right_band: list[str]

    def linear(self) -> list[str]: return self.left_band + self.right_band
    def view(self) -> str: return " ".join(self.left_band + ["|"] + self.right_band)
    def to_raw_tape(self) -> dict[int, str]: return materialize_raw_tape(self.left_band, self.right_band)

    @property
    def outer_tape(self) -> dict[int, str]: return self.to_raw_tape()

    @classmethod
    def from_raw_tape(cls, encoding: Encoding, outer_tape: dict[int, str]) -> "EncodedBand":
        left_band, right_band = split_outer_tape(outer_tape)
        return cls(encoding, left_band, right_band)


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


def materialize_raw_tape(left_band: list[str], right_band: list[str]) -> dict[int, str]:
    raw_tape = defaultdict(lambda: OUTER_BLANK)
    raw_tape.update(place_on_negative_side(left_band, start=-1))
    raw_tape.update(place_on_positive_side(right_band, start=0))
    return raw_tape


def split_outer_tape(outer_tape: dict[int, str]) -> tuple[list[str], list[str]]:
    live_cells = [address for address, symbol in outer_tape.items() if symbol != OUTER_BLANK]
    if not live_cells:
        return [], []
    lowest, highest = min(live_cells), max(live_cells)
    return [outer_tape[address] for address in range(lowest, 0)], [outer_tape[address] for address in range(0, highest + 1)]


def split_raw_tape(raw_tape: dict[int, str]) -> tuple[list[str], list[str]]: return split_outer_tape(raw_tape)


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
    return EncodedBand(encoding, left_band, right_band)


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


def compile_tm_to_encoded_band(
    tm_program: TMProgram,
    input_symbols: Iterable[str],
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    blanks_left: int = 0,
    blanks_right: int = 8,
) -> EncodedBand:
    return compile_tm_to_universal_tape(
        tm_program,
        input_symbols,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=blank,
        blanks_left=blanks_left,
        blanks_right=blanks_right,
    )


__all__ = [
    "CELL",
    "CMP_FLAG",
    "CUR_STATE",
    "CUR_SYMBOL",
    "END_CELL",
    "END_FIELD",
    "END_REGS",
    "END_RULE",
    "END_RULES",
    "END_TAPE",
    "EncodedBand",
    "HEAD",
    "MOVE",
    "MOVE_DIR",
    "NEXT",
    "NEXT_STATE",
    "NO_HEAD",
    "OUTER_BLANK",
    "READ",
    "REGS",
    "RULE",
    "RULES",
    "STATE",
    "TAPE",
    "TMP",
    "WRITE",
    "WRITE_SYMBOL",
    "build_outer_tape",
    "build_register_band",
    "build_rule_band",
    "build_tape_band",
    "compile_tm_to_universal_tape",
    "compile_tm_to_encoded_band",
    "materialize_raw_tape",
    "place_on_negative_side",
    "place_on_positive_side",
    "split_raw_tape",
    "split_outer_tape",
    "wrap_field",
]
