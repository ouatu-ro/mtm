"""Declared head-position expectations for lowered routines.

The UTM backend is mostly a choreography problem: many routines only work if
the simulated machine's head is already at a particular marker, and they leave
the head at another meaningful place for the next routine. These contracts make
that protocol visible on the Routine object.

They are intentionally lightweight. They are not a proof system; they are
structured documentation that tests and later validators can inspect without
parsing English strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class HeadAnywhere:
    """No useful claim about the head position."""

    pass


@dataclass(frozen=True)
class HeadOnRuntimeTape:
    """The head is somewhere on the encoded runtime tape."""

    pass


@dataclass(frozen=True)
class HeadAt:
    """The head is positioned on one specific marker symbol."""

    marker: str


@dataclass(frozen=True)
class HeadAtOneOf:
    """The head is positioned on one marker from a known set."""

    markers: tuple[str, ...]


HeadContract: TypeAlias = HeadAnywhere | HeadOnRuntimeTape | HeadAt | HeadAtOneOf

__all__ = ["HeadAnywhere", "HeadAt", "HeadAtOneOf", "HeadContract", "HeadOnRuntimeTape"]
