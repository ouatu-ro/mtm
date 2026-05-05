"""Routine-level lowering operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .constants import Label, Symbol


@dataclass(frozen=True)
class EmitOp:
    source: Label
    read: Symbol
    target: Label
    write: Symbol
    move: int


@dataclass(frozen=True)
class EmitAllOp:
    source: Label
    target: Label
    move: int


@dataclass(frozen=True)
class SeekOp:
    source: Label
    target: Label
    markers: frozenset[str]
    direction: str


@dataclass(frozen=True)
class MoveStepsOp:
    source: Label
    target: Label
    steps: int
    direction: str


@dataclass(frozen=True)
class BranchOnBitOp:
    source: Label
    zero: Label
    one: Label
    move: int


@dataclass(frozen=True)
class WriteBitOp:
    source: Label
    target: Label
    bit: str
    move: int


@dataclass(frozen=True)
class BranchAtOp:
    source: Label
    marker: str
    label_true: Label
    label_false: Label


@dataclass(frozen=True)
class EmitAnyExceptOp:
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
