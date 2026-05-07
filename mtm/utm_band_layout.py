"""Concrete band layout for universal-machine input.

The runtime input has two bands: registers and rules on the left side,
simulated source tape on the right side. This module owns that marker
vocabulary and the conversion from split bands to the raw tape consumed by the
lowered universal machine.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Iterable

from .source_encoding import Encoding, TMAbi, TMProgram, build_encoding, encode_direction, encode_state, encode_symbol, infer_minimal_abi, L, R

if TYPE_CHECKING:
    from .semantic_objects import SourceTape

REGS, END_REGS, RULES, RULE, END_RULE, END_RULES = "#REGS", "#END_REGS", "#RULES", "#RULE", "#END_RULE", "#END_RULES"
TAPE_LEFT, END_TAPE_LEFT = "#TAPE_LEFT", "#END_TAPE_LEFT"
TAPE, END_TAPE, CELL = "#TAPE", "#END_TAPE", "#CELL"
END_FIELD, END_CELL = "#END_FIELD", "#END_CELL"

CUR_STATE, CUR_SYMBOL, WRITE_SYMBOL, NEXT_STATE = "#CUR_STATE", "#CUR_SYMBOL", "#WRITE_SYMBOL", "#NEXT_STATE"
MOVE_DIR, HALT_STATE, BLANK_SYMBOL = "#MOVE_DIR", "#HALT_STATE", "#BLANK_SYMBOL"
LEFT_DIR, RIGHT_DIR, CMP_FLAG, TMP = "#LEFT_DIR", "#RIGHT_DIR", "#CMP_FLAG", "#TMP"
STATE, READ, WRITE, NEXT, MOVE = "#STATE", "#READ", "#WRITE", "#NEXT", "#MOVE"
HEAD, NO_HEAD = "#HEAD", "#NO_HEAD"
RUNTIME_BLANK = "_RUNTIME_BLANK"

UTM_STRUCTURAL_ALPHABET = (
    "0", "1",
    REGS, END_REGS, RULES, RULE, END_RULE, END_RULES,
    TAPE_LEFT, END_TAPE_LEFT, TAPE, END_TAPE, CELL,
    END_FIELD, END_CELL,
    CUR_STATE, CUR_SYMBOL, WRITE_SYMBOL, NEXT_STATE,
    MOVE_DIR, HALT_STATE, BLANK_SYMBOL, LEFT_DIR, RIGHT_DIR, CMP_FLAG, TMP,
    STATE, READ, WRITE, NEXT, MOVE,
    HEAD, NO_HEAD,
)


@dataclass(frozen=True)
class EncodedTape:
    """Concrete left/right band token layout for one encoded UTM input."""

    encoding: Encoding; left_band: list[str]; right_band: list[str]
    minimal_abi: TMAbi | None = None; target_abi: TMAbi | None = None

    def linear(self) -> list[str]:
        """Return all concrete tokens without the left/right split."""

        return self.left_band + self.right_band

    def view(self) -> str:
        """Return a compact text view of the split bands."""

        return " ".join(self.left_band + ["|"] + self.right_band)

    def to_runtime_tape(self) -> dict[int, str]:
        """Place the split bands onto the raw integer-addressed runtime tape."""

        return materialize_runtime_tape(self.left_band, self.right_band)

    @property
    def runtime_tape(self) -> dict[int, str]: return self.to_runtime_tape()

    @classmethod
    def from_runtime_tape(cls, encoding: Encoding, runtime_tape: dict[int, str]) -> "EncodedTape":
        left_band, right_band = split_runtime_tape(runtime_tape)
        return cls(encoding, left_band, right_band)


def wrap_field(marker: str, payload: Iterable[str]) -> list[str]: return [marker, *payload, END_FIELD]


def build_register_band(encoding: Encoding) -> list[str]:
    """Build the initial register block for one encoded source machine."""

    temp_width = max(encoding.state_width, encoding.symbol_width, encoding.direction_width)
    return [
        REGS,
        *wrap_field(CUR_STATE, encode_state(encoding, encoding.initial_state)),
        *wrap_field(CUR_SYMBOL, encode_symbol(encoding, encoding.blank)),
        *wrap_field(WRITE_SYMBOL, encode_symbol(encoding, encoding.blank)),
        *wrap_field(NEXT_STATE, encode_state(encoding, encoding.initial_state)),
        *wrap_field(MOVE_DIR, encode_direction(encoding, L)),
        *wrap_field(HALT_STATE, encode_state(encoding, encoding.halt_state)),
        *wrap_field(BLANK_SYMBOL, encode_symbol(encoding, encoding.blank)),
        *wrap_field(LEFT_DIR, encode_direction(encoding, L)),
        *wrap_field(RIGHT_DIR, encode_direction(encoding, R)),
        *wrap_field(CMP_FLAG, ("0",)),
        *wrap_field(TMP, ("0",) * temp_width),
        END_REGS,
    ]


def build_rule_band(encoding: Encoding, tm_program: TMProgram) -> list[str]:
    """Encode every source transition into the rule block."""

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


def build_left_tape_band_from_source_tape(encoding: Encoding, source_tape: "SourceTape") -> list[str]:
    """Build the encoded negative side of the simulated source tape."""

    band = [END_TAPE_LEFT]
    first_address = -len(source_tape.left_band)
    for index, symbol in enumerate(source_tape.left_band):
        address = first_address + index
        band.extend([CELL, HEAD if address == source_tape.head else NO_HEAD, *encode_symbol(encoding, symbol), END_CELL])
    return band + [TAPE_LEFT]


def build_tape_band_from_source_tape(encoding: Encoding, source_tape: "SourceTape") -> list[str]:
    """Build the encoded nonnegative side of the simulated source tape."""

    band = [TAPE]
    for index, symbol in enumerate(source_tape.right_band):
        band.extend([CELL, HEAD if index == source_tape.head else NO_HEAD, *encode_symbol(encoding, symbol), END_CELL])
    return band + [END_TAPE]


def place_on_negative_side(tokens: list[str], *, start: int = -1) -> dict[int, str]: return {start - (len(tokens) - 1 - index): token for index, token in enumerate(tokens)}
def place_on_positive_side(tokens: list[str], *, start: int = 0) -> dict[int, str]: return {start + index: token for index, token in enumerate(tokens)}


def materialize_runtime_tape(left_band: list[str], right_band: list[str]) -> dict[int, str]:
    """Place left-band tokens at negative addresses and right-band tokens at nonnegative addresses."""

    runtime_tape = defaultdict(lambda: RUNTIME_BLANK)
    runtime_tape.update(place_on_negative_side(left_band, start=-1))
    runtime_tape.update(place_on_positive_side(right_band, start=0))
    return runtime_tape


def split_runtime_tape(runtime_tape: dict[int, str]) -> tuple[list[str], list[str]]:
    """Recover left and right band token lists from a runtime tape dictionary."""

    live_cells = [address for address, symbol in runtime_tape.items() if symbol != RUNTIME_BLANK]
    if not live_cells:
        return [], []
    lowest, highest = min(live_cells), max(live_cells)
    return [runtime_tape[address] for address in range(lowest, 0)], [runtime_tape[address] for address in range(0, highest + 1)]


def _target_abi_from_minimal_abi(minimal_abi: TMAbi) -> TMAbi:
    return TMAbi(
        state_width=minimal_abi.state_width,
        symbol_width=minimal_abi.symbol_width,
        dir_width=minimal_abi.dir_width,
        grammar_version=minimal_abi.grammar_version,
        family_label=f"U[Wq={minimal_abi.state_width},Ws={minimal_abi.symbol_width},Wd={minimal_abi.dir_width}]",
    )


def compile_tm_to_universal_tape(
    tm_program: TMProgram,
    source_tape: "SourceTape",
    *,
    initial_state: str,
    halt_state: str,
    abi: TMAbi | None = None,
) -> EncodedTape:
    """Compile a source TM and source tape into concrete UTM input bands."""

    if tm_program.blank != source_tape.blank:
        raise ValueError(
            f"source blank mismatch: TMProgram.blank={tm_program.blank!r} "
            f"!= SourceTape.blank={source_tape.blank!r}"
        )
    minimal_abi = infer_minimal_abi(
        tm_program,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=source_tape.blank,
        source_symbols=source_tape.cells,
    )
    target_abi = _target_abi_from_minimal_abi(minimal_abi) if abi is None else abi
    encoding = build_encoding(
        tm_program,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=source_tape.blank,
        source_symbols=source_tape.cells,
        abi=target_abi,
    )
    left_band = build_left_tape_band_from_source_tape(encoding, source_tape)
    left_band += build_register_band(encoding) + build_rule_band(encoding, tm_program)
    right_band = build_tape_band_from_source_tape(encoding, source_tape)
    return EncodedTape(encoding, left_band, right_band, minimal_abi=minimal_abi, target_abi=target_abi)


__all__ = ["BLANK_SYMBOL", "CELL", "CMP_FLAG", "CUR_STATE", "CUR_SYMBOL", "END_CELL", "END_FIELD", "END_REGS", "END_RULE",
           "END_RULES", "END_TAPE", "EncodedTape", "HALT_STATE", "HEAD", "LEFT_DIR", "MOVE", "MOVE_DIR", "NEXT", "NEXT_STATE", "NO_HEAD",
           "RIGHT_DIR", "RUNTIME_BLANK", "READ", "REGS", "RULE", "RULES", "STATE", "TAPE", "TAPE_LEFT",
           "END_TAPE_LEFT", "TMP", "WRITE", "WRITE_SYMBOL", "build_left_tape_band_from_source_tape",
           "UTM_STRUCTURAL_ALPHABET", "build_register_band", "build_rule_band", "build_tape_band_from_source_tape",
           "compile_tm_to_universal_tape", "materialize_runtime_tape", "place_on_negative_side",
           "place_on_positive_side", "split_runtime_tape", "wrap_field"]
