"""Routine objects and symbolic name allocation."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import Label
from .contracts import HeadAnywhere, HeadContract
from .ops import Op


@dataclass(frozen=True)
class Routine:
    name: str
    entry: Label
    exits: tuple[Label, ...]
    falls_through: bool
    ops: tuple[Op, ...]
    requires: HeadContract = HeadAnywhere()
    ensures: HeadContract = HeadAnywhere()


class NameSupply:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self._fresh_ids: dict[str, int] = {}
        self._named: dict[str, str] = {}

    def fresh(self, hint: str) -> str:
        clean_hint = hint.replace("@", "").replace("#", "").replace(" ", "_")
        next_id = self._fresh_ids.get(clean_hint, 0)
        self._fresh_ids[clean_hint] = next_id + 1
        return f"{self.prefix}_{clean_hint}_{next_id}"

    def named(self, local_label: str) -> str:
        if local_label not in self._named:
            clean_label = local_label.replace("@", "").replace("#", "").replace(" ", "_")
            self._named[local_label] = self.fresh(clean_label)
        return self._named[local_label]


class RoutineDraft:
    def __init__(
        self,
        name: str,
        *,
        entry: Label,
        exits: tuple[Label, ...],
        falls_through: bool = True,
        requires: HeadContract = HeadAnywhere(),
        ensures: HeadContract = HeadAnywhere(),
    ):
        self.name = name
        self.entry = entry
        self.exits = exits
        self.falls_through = falls_through
        self.requires = requires
        self.ensures = ensures
        self.ops: list[Op] = []
        self._local_ids: dict[str, int] = {}

    def local(self, hint: str) -> Label:
        next_id = self._local_ids.get(hint, 0)
        self._local_ids[hint] = next_id + 1
        return f"@{hint}_{next_id}"

    def add(self, op: Op) -> None:
        self.ops.append(op)

    def build(self) -> Routine:
        return Routine(
            name=self.name,
            entry=self.entry,
            exits=self.exits,
            falls_through=self.falls_through,
            ops=tuple(self.ops),
            requires=self.requires,
            ensures=self.ensures,
        )


__all__ = ["NameSupply", "Routine", "RoutineDraft"]
