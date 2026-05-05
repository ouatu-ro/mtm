"""Raw transition-machine program, builder, and interpreter.

This is the lowest-level representation in the project: a transition table
mapping ``(state, read_symbol)`` to ``(next_state, write_symbol, move)``. The
compiler backend lowers structured objects into this form only at the final
assembly boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

L, S, R = -1, 0, 1

TransitionKey = tuple[str, str]
Transition = tuple[str, str, int]


@dataclass(frozen=True)
class TMTransitionProgram:
    """An immutable raw transition table plus its execution metadata."""

    prog: dict[TransitionKey, Transition]
    start_state: str
    halt_state: str
    alphabet: tuple[str, ...]
    blank: str = "_RUNTIME_BLANK"

    @property
    def transitions(self) -> Mapping[TransitionKey, Transition]:
        """Read-only conceptual alias for the raw transition relation."""

        return MappingProxyType(self.prog)

    def write(self, path: str | "Path") -> None:
        """Write this program as a ``.tm`` artifact."""

        from .artifacts import write_tm

        write_tm(path, self)

    @classmethod
    def read(cls, path: str | "Path") -> "TMTransitionProgram":
        """Read a ``.tm`` artifact into a transition program."""

        from .artifacts import read_tm

        return read_tm(path)

    def to_artifact(self, *, target_abi=None, minimal_abi=None):
        """Wrap this program in the semantic UTM program artifact object."""

        from .semantic_objects import UTMProgramArtifact

        return UTMProgramArtifact(
            program=self,
            target_abi=target_abi,
            minimal_abi=minimal_abi,
        )


class TMBuilder:
    """Mutable transition-table builder used only at assembly boundaries."""

    def __init__(self, alphabet: Iterable[str], *, halt_state: str = "U_HALT", blank: str = "_RUNTIME_BLANK"):
        self.alphabet = tuple(dict.fromkeys([blank, *alphabet]))
        self.halt_state = halt_state
        self.blank = blank
        self.prog: dict[TransitionKey, Transition] = {}
        self._fresh_ids: dict[str, int] = {}
        self._labels: dict[str, str] = {halt_state: halt_state}

    def fresh(self, prefix: str) -> str:
        """Allocate a readable state name with a numeric suffix."""

        next_id = self._fresh_ids.get(prefix, 0)
        self._fresh_ids[prefix] = next_id + 1
        return f"{prefix}_{next_id}"

    def label_state(self, label: str) -> str:
        """Return a stable state name for an external label."""

        return self._labels.setdefault(label, label)

    def emit(self, state: str, read: str, next_state: str, write: str, move: int) -> None:
        """Add one transition row, rejecting duplicate ``(state, read)`` keys."""

        key = (state, read)
        if key in self.prog:
            raise ValueError(f"duplicate transition for {key!r}")
        self.prog[key] = (next_state, write, move)

    def emit_all(self, state: str, next_state: str, *, move: int = S) -> None:
        """Add one preserve-symbol transition for every alphabet symbol."""

        for symbol in self.alphabet:
            self.emit(state, symbol, next_state, symbol, move)

    def build(self, start_state: str) -> TMTransitionProgram:
        """Freeze the builder into a TMTransitionProgram."""

        return TMTransitionProgram(self.prog, start_state=start_state, halt_state=self.halt_state, alphabet=self.alphabet, blank=self.blank)


def run_raw_tm(tm: TMTransitionProgram, tape: dict[int, str], *, head: int = 0, state: str | None = None, max_steps: int = 100):
    """Run a raw transition program on a sparse tape dictionary."""

    tape, state = dict(tape), (tm.start_state if state is None else state)
    steps = 0
    while state != tm.halt_state and steps < max_steps:
        read = tape.get(head, tm.blank)
        transition = tm.prog.get((state, read))
        if transition is None:
            return {"status": "stuck", "state": state, "head": head, "tape": tape, "steps": steps}
        next_state, write, move = transition
        tape[head], state, head, steps = write, next_state, head + move, steps + 1
    return {"status": "halted" if state == tm.halt_state else "fuel_exhausted", "state": state, "head": head, "tape": tape, "steps": steps}


def format_raw_tm(tm: TMTransitionProgram) -> str:
    """Format a raw transition program as a readable literal artifact body."""

    rows = []
    for (state, read), (next_state, write, move) in sorted(tm.prog.items()):
        rows.append(f"    ({state!r}, {read!r}): ({next_state!r}, {write!r}, {move}),")
    return "\n".join([
        "raw_tm = {",
        *rows,
        "}",
        f"start_state = {tm.start_state!r}",
        f"halt_state = {tm.halt_state!r}",
        f"blank = {tm.blank!r}",
    ])


__all__ = ["L", "R", "S", "TMBuilder", "TMTransitionProgram", "format_raw_tm", "run_raw_tm"]
