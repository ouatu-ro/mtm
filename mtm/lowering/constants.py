"""Shared lowering constants and symbolic names."""

from __future__ import annotations

from typing import TypeAlias

from ..raw_transition_tm import L, R, S
from ..utm_band_layout import CMP_FLAG, CUR_STATE, CUR_SYMBOL, MOVE_DIR, NEXT_STATE, TMP, WRITE_SYMBOL

Label: TypeAlias = str
State: TypeAlias = str
Symbol: TypeAlias = str

GLOBAL_MARKERS = (CUR_STATE, CUR_SYMBOL, WRITE_SYMBOL, NEXT_STATE, MOVE_DIR, CMP_FLAG, TMP)
ACTIVE_RULE = "#ACTIVE_RULE"
VALID_MOVES = {L, S, R}


def move_for_direction(direction: str) -> int:
    if direction == "R":
        return R
    if direction == "L":
        return L
    raise ValueError(f"unsupported direction: {direction!r}")


def global_direction(src_marker: str, dst_marker: str) -> str:
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
