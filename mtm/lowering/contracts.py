"""Head-position contracts for lowered routines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class HeadAnywhere:
    pass


@dataclass(frozen=True)
class HeadOnRuntimeTape:
    pass


@dataclass(frozen=True)
class HeadAt:
    marker: str


@dataclass(frozen=True)
class HeadAtOneOf:
    markers: tuple[str, ...]


HeadContract: TypeAlias = HeadAnywhere | HeadOnRuntimeTape | HeadAt | HeadAtOneOf

__all__ = ["HeadAnywhere", "HeadAt", "HeadAtOneOf", "HeadContract", "HeadOnRuntimeTape"]
