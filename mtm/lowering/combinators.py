"""Reusable choreography for routine construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .constants import Label
from .ops import BranchOnBitOp, EmitOp, MoveStepsOp, SeekOp, WriteBitOp
from .routines import RoutineDraft

Bit: TypeAlias = str
BIT_VALUES: tuple[Bit, Bit] = ("0", "1")


@dataclass(frozen=True)
class BitBranch:
    state: Label
    bit: Bit


def seek(draft: RoutineDraft, source: Label, *, markers: set[str], direction: str, target: Label) -> None:
    draft.add(SeekOp(source, target, frozenset(markers), direction))


def move_steps(draft: RoutineDraft, source: Label, *, steps: int, direction: str, target: Label) -> None:
    draft.add(MoveStepsOp(source, target, steps, direction))


def branch_on_bit(draft: RoutineDraft, source: Label, *, zero_label: Label, one_label: Label, move: int) -> None:
    draft.add(BranchOnBitOp(source, zero_label, one_label, move))


def branch_bit_at_offset(
    draft: RoutineDraft,
    source: Label,
    *,
    offset: int,
    move_after_read: int,
    prefix: str,
    index: int,
) -> tuple[BitBranch, BitBranch]:
    read_state = draft.local(f"{prefix}_read_{index}")
    zero_state = draft.local(f"{prefix}_bit0_{index}")
    one_state = draft.local(f"{prefix}_bit1_{index}")
    move_steps(draft, source, steps=offset, direction="R", target=read_state)
    branch_on_bit(draft, read_state, zero_label=zero_state, one_label=one_state, move=move_after_read)
    return (BitBranch(zero_state, "0"), BitBranch(one_state, "1"))


def emit_expected_bit_branch(
    draft: RoutineDraft,
    source: Label,
    *,
    expected: Bit,
    match_target: Label,
    mismatch_target: Label,
    match_move: int,
    mismatch_move: int,
) -> None:
    if expected not in BIT_VALUES:
        raise ValueError(f"expected bit must be 0 or 1: {expected!r}")
    mismatch = "1" if expected == "0" else "0"
    draft.add(EmitOp(source, expected, match_target, expected, match_move))
    draft.add(EmitOp(source, mismatch, mismatch_target, mismatch, mismatch_move))


def require_bit(bit: str) -> None:
    if bit not in BIT_VALUES:
        raise ValueError(f"bit must be 0 or 1: {bit!r}")


def write_current_bit(draft: RoutineDraft, source: Label, *, bit: str, target: Label, move: int) -> None:
    require_bit(bit)
    draft.add(WriteBitOp(source, target, bit, move))


def write_bit_at_offset(
    draft: RoutineDraft,
    source: Label,
    *,
    bit: Bit,
    offset: int,
    target: Label,
    write_move: int,
    prefix: str,
    index: int,
) -> None:
    require_bit(bit)
    write_state = draft.local(f"{prefix}_write_{bit}_{index}")
    move_steps(draft, source, steps=offset, direction="R", target=write_state)
    write_current_bit(draft, write_state, bit=bit, target=target, move=write_move)


def seek_then_write_bit_at_offset(
    draft: RoutineDraft,
    source: Label,
    *,
    marker: str,
    seek_direction: str,
    bit: Bit,
    offset: int,
    target: Label,
    write_move: int,
    prefix: str,
    index: int,
) -> None:
    require_bit(bit)
    marker_state = draft.local(f"{prefix}_marker_{bit}_{index}")
    seek(draft, source, markers={marker}, direction=seek_direction, target=marker_state)
    write_bit_at_offset(
        draft,
        marker_state,
        bit=bit,
        offset=offset,
        target=target,
        write_move=write_move,
        prefix=prefix,
        index=index,
    )


__all__ = [
    "BIT_VALUES",
    "Bit",
    "BitBranch",
    "branch_bit_at_offset",
    "branch_on_bit",
    "emit_expected_bit_branch",
    "move_steps",
    "require_bit",
    "seek",
    "seek_then_write_bit_at_offset",
    "write_bit_at_offset",
    "write_current_bit",
]
