"""Compiled runtime-band layout for encoded source Turing machines.

Primary public names use ``runtime_tape`` vocabulary.
``outer_tape`` and ``raw_tape`` remain compatibility aliases for now.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Iterable

from .tape_encoding import Encoding, TMAbi, TMProgramLike, build_encoding, coerce_tm_program, encode_direction, encode_state, encode_symbol, infer_minimal_abi, L, R

if TYPE_CHECKING:
    from .semantic_objects import TMBand

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
    minimal_abi: TMAbi | None = None; target_abi: TMAbi | None = None

    def linear(self) -> list[str]: return self.left_band + self.right_band
    def view(self) -> str: return " ".join(self.left_band + ["|"] + self.right_band)
    def to_runtime_tape(self) -> dict[int, str]: return materialize_runtime_tape(self.left_band, self.right_band)
    # Compatibility alias for older callers that still expect "raw" tape wording.
    def to_raw_tape(self) -> dict[int, str]: return self.to_runtime_tape()

    @property
    def runtime_tape(self) -> dict[int, str]: return self.to_runtime_tape()

    # Compatibility alias for older callers that still use "outer_tape".
    @property
    def outer_tape(self) -> dict[int, str]: return self.runtime_tape

    @classmethod
    def from_runtime_tape(cls, encoding: Encoding, runtime_tape: dict[int, str]) -> "EncodedBand":
        left_band, right_band = split_runtime_tape(runtime_tape)
        return cls(encoding, left_band, right_band)

    @classmethod
    def from_raw_tape(cls, encoding: Encoding, raw_tape: dict[int, str]) -> "EncodedBand":
        left_band, right_band = split_raw_tape(raw_tape)
        return cls(encoding, left_band, right_band)

    @classmethod
    def from_outer_tape(cls, encoding: Encoding, outer_tape: dict[int, str]) -> "EncodedBand":
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


def build_rule_band(encoding: Encoding, tm_program: TMProgramLike) -> list[str]:
    program = coerce_tm_program(tm_program)
    band = [RULES]
    for (state, read_symbol), (next_state, write_symbol, move_direction) in program.items():
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


def build_tape_band_from_source_band(encoding: Encoding, source_band: "TMBand") -> list[str]:
    band = [TAPE]
    for index, symbol in enumerate(source_band.cells):
        band.extend([CELL, HEAD if index == source_band.head else NO_HEAD, *encode_symbol(encoding, symbol), END_CELL])
    return band + [END_TAPE]


def place_on_negative_side(tokens: list[str], *, start: int = -1) -> dict[int, str]: return {start - (len(tokens) - 1 - index): token for index, token in enumerate(tokens)}
def place_on_positive_side(tokens: list[str], *, start: int = 0) -> dict[int, str]: return {start + index: token for index, token in enumerate(tokens)}


def materialize_runtime_tape(left_band: list[str], right_band: list[str]) -> dict[int, str]:
    raw_tape = defaultdict(lambda: OUTER_BLANK)
    raw_tape.update(place_on_negative_side(left_band, start=-1))
    raw_tape.update(place_on_positive_side(right_band, start=0))
    return raw_tape


materialize_raw_tape = materialize_runtime_tape


def split_runtime_tape(runtime_tape: dict[int, str]) -> tuple[list[str], list[str]]:
    live_cells = [address for address, symbol in runtime_tape.items() if symbol != OUTER_BLANK]
    if not live_cells:
        return [], []
    lowest, highest = min(live_cells), max(live_cells)
    return [runtime_tape[address] for address in range(lowest, 0)], [runtime_tape[address] for address in range(0, highest + 1)]


split_raw_tape = split_runtime_tape


split_outer_tape = split_runtime_tape


def _coerce_source_band(
    source: Iterable[str] | "TMBand",
    *,
    blank: str,
    blanks_left: int,
    blanks_right: int,
) -> "TMBand":
    from .semantic_objects import TMBand

    if isinstance(source, TMBand):
        if blank != source.blank:
            raise ValueError(f"blank mismatch: source band uses {source.blank!r}, compile path requested {blank!r}")
        return source
    return TMBand(
        cells=tuple([blank] * blanks_left + list(source) + [blank] * blanks_right),
        head=blanks_left,
        blank=blank,
    )


def _target_abi_from_minimal_abi(minimal_abi: TMAbi) -> TMAbi:
    return TMAbi(
        state_width=minimal_abi.state_width,
        symbol_width=minimal_abi.symbol_width,
        dir_width=minimal_abi.dir_width,
        grammar_version=minimal_abi.grammar_version,
        family_label=f"U[Wq={minimal_abi.state_width},Ws={minimal_abi.symbol_width},Wd={minimal_abi.dir_width}]",
    )


def build_encoded_band(
    tm_program: TMProgramLike,
    source: Iterable[str] | "TMBand",
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    blanks_left: int = 0,
    blanks_right: int = 8,
    abi: TMAbi | None = None,
) -> EncodedBand:
    source_band = _coerce_source_band(source, blank=blank, blanks_left=blanks_left, blanks_right=blanks_right)
    minimal_abi = infer_minimal_abi(
        tm_program,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=source_band.blank,
        source_symbols=source_band.cells,
    )
    target_abi = _target_abi_from_minimal_abi(minimal_abi) if abi is None else abi
    encoding = build_encoding(
        tm_program,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=source_band.blank,
        source_symbols=source_band.cells,
        abi=target_abi,
    )
    left_band = build_register_band(encoding) + build_rule_band(encoding, tm_program)
    right_band = build_tape_band_from_source_band(encoding, source_band)
    return EncodedBand(encoding, left_band, right_band, minimal_abi=minimal_abi, target_abi=target_abi)


def build_outer_tape(
    tm_program: TMProgramLike,
    source: Iterable[str] | "TMBand",
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    blanks_left: int = 0,
    blanks_right: int = 8,
    abi: TMAbi | None = None,
) -> EncodedBand:
    """Compatibility alias for build_encoded_band()."""
    return build_encoded_band(
        tm_program,
        source,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=blank,
        blanks_left=blanks_left,
        blanks_right=blanks_right,
        abi=abi,
    )


def compile_tm_to_universal_tape(
    tm_program: TMProgramLike,
    source: Iterable[str] | "TMBand",
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    blanks_left: int = 0,
    blanks_right: int = 8,
    abi: TMAbi | None = None,
) -> EncodedBand:
    return build_encoded_band(
        tm_program,
        source,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=blank,
        blanks_left=blanks_left,
        blanks_right=blanks_right,
        abi=abi,
    )


def compile_tm_to_encoded_band(
    tm_program: TMProgramLike,
    source: Iterable[str] | "TMBand",
    *,
    initial_state: str,
    halt_state: str,
    blank: str = "_",
    blanks_left: int = 0,
    blanks_right: int = 8,
    abi: TMAbi | None = None,
) -> EncodedBand:
    return compile_tm_to_universal_tape(
        tm_program,
        source,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=blank,
        blanks_left=blanks_left,
        blanks_right=blanks_right,
        abi=abi,
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
    "build_encoded_band",
    "build_outer_tape",
    "build_register_band",
    "build_rule_band",
    "build_tape_band",
    "build_tape_band_from_source_band",
    "compile_tm_to_universal_tape",
    "compile_tm_to_encoded_band",
    "materialize_raw_tape",
    "materialize_runtime_tape",
    "place_on_negative_side",
    "place_on_positive_side",
    "split_raw_tape",
    "split_runtime_tape",
    "split_outer_tape",
    "wrap_field",
]
