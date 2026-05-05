"""Small operations used inside Routine objects.

These operations are deliberately above raw TM transitions. For example,
``SeekOp`` means "scan until one of these markers is found"; it is expanded
into concrete transition rows only when a Routine is compiled to a CFG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .constants import Label, Symbol


@dataclass(frozen=True)
class EmitOp:
    """One explicit transition shape: on one symbol, write one symbol."""

    source: Label
    read: Symbol
    target: Label
    write: Symbol
    move: int


@dataclass(frozen=True)
class EmitAllOp:
    """Transition on every alphabet symbol, preserving the read symbol."""

    source: Label
    target: Label
    move: int


@dataclass(frozen=True)
class SeekOp:
    """Scan in one direction until any marker in ``markers`` is under the head."""

    source: Label
    target: Label
    markers: frozenset[str]
    direction: str


@dataclass(frozen=True)
class MoveStepsOp:
    """Move a fixed number of cells while preserving every symbol."""

    source: Label
    target: Label
    steps: int
    direction: str


@dataclass(frozen=True)
class BranchOnBitOp:
    """Branch on a binary cell whose symbol must be ``0`` or ``1``."""

    source: Label
    zero: Label
    one: Label
    move: int


@dataclass(frozen=True)
class WriteBitOp:
    """Write the same bit whether the current bit is ``0`` or ``1``."""

    source: Label
    target: Label
    bit: str
    move: int


@dataclass(frozen=True)
class BranchAtOp:
    """Branch according to whether the current cell is a marker."""

    source: Label
    marker: str
    label_true: Label
    label_false: Label


@dataclass(frozen=True)
class EmitAnyExceptOp:
    """Transition on every alphabet symbol except one symbol."""

    source: Label
    except_symbol: Symbol
    target: Label
    move: int


Op: TypeAlias = EmitOp | EmitAllOp | SeekOp | MoveStepsOp | BranchOnBitOp | WriteBitOp | BranchAtOp | EmitAnyExceptOp

__all__ = [
    "BranchAtOp",
    "BranchOnBitOp",
    "EmitAllOp",
    "EmitAnyExceptOp",
    "EmitOp",
    "MoveStepsOp",
    "Op",
    "SeekOp",
    "WriteBitOp",
]
