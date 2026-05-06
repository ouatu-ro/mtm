"""Names shared by the lowering backend.

This module is deliberately small: it holds the symbolic state/symbol aliases,
the movement constants from the raw transition-machine layer, and layout facts
that are needed by more than one lowering phase. Anything that emits routine
ops or understands a Meta-ASM instruction belongs elsewhere.
"""

from __future__ import annotations

from typing import TypeAlias

from ..raw_transition_tm import L, R, S
from ..utm_band_layout import BLANK_SYMBOL, CMP_FLAG, CUR_STATE, CUR_SYMBOL, HALT_STATE, LEFT_DIR, MOVE_DIR, NEXT_STATE, RIGHT_DIR, TMP, WRITE_SYMBOL

Label: TypeAlias = str
State: TypeAlias = str
Symbol: TypeAlias = str

GLOBAL_MARKERS = (
    CUR_STATE,
    CUR_SYMBOL,
    WRITE_SYMBOL,
    NEXT_STATE,
    MOVE_DIR,
    HALT_STATE,
    BLANK_SYMBOL,
    LEFT_DIR,
    RIGHT_DIR,
    CMP_FLAG,
    TMP,
)
ACTIVE_RULE = "#ACTIVE_RULE"
VALID_MOVES = {L, S, R}


def move_for_direction(direction: str) -> int:
    """Translate a textual scan direction into a raw TM movement."""

    if direction == "R":
        return R
    if direction == "L":
        return L
    raise ValueError(f"unsupported direction: {direction!r}")


def global_direction(src_marker: str, dst_marker: str) -> str:
    """Return the scan direction between two global-register markers."""

    return "R" if GLOBAL_MARKERS.index(src_marker) < GLOBAL_MARKERS.index(dst_marker) else "L"


__all__ = [
    "ACTIVE_RULE",
    "GLOBAL_MARKERS",
    "L",
    "Label",
    "R",
    "S",
    "State",
    "Symbol",
    "VALID_MOVES",
    "global_direction",
    "move_for_direction",
]
