"""Tiny raw-TM builder and runner."""

from __future__ import annotations

from dataclasses import dataclass

L, S, R = -1, 0, 1

TransitionKey = tuple[str, str]
Transition = tuple[str, str, int]


@dataclass(frozen=True)
class RawTM:
    prog: dict[TransitionKey, Transition]
    start_state: str
    halt_state: str
    alphabet: tuple[str, ...]
    blank: str = "_OUTER_BLANK"


class TMBuilder:
    def __init__(self, alphabet: list[str] | tuple[str, ...], *, halt_state: str = "U_HALT", blank: str = "_OUTER_BLANK"):
        self.alphabet = tuple(dict.fromkeys(alphabet))
        self.halt_state = halt_state
        self.blank = blank
        self.prog: dict[TransitionKey, Transition] = {}
        self._fresh_ids: dict[str, int] = {}
        self._labels: dict[str, str] = {halt_state: halt_state}

    def fresh(self, prefix: str) -> str:
        next_id = self._fresh_ids.get(prefix, 0)
        self._fresh_ids[prefix] = next_id + 1
        return f"{prefix}_{next_id}"

    def label_state(self, label: str) -> str:
        return self._labels.setdefault(label, label)

    def emit(self, state: str, read: str, next_state: str, write: str, move: int) -> None:
        key = (state, read)
        if key in self.prog:
            raise ValueError(f"duplicate transition for {key!r}")
        self.prog[key] = (next_state, write, move)

    def emit_all(self, state: str, next_state: str, *, move: int = S) -> None:
        for symbol in self.alphabet:
            self.emit(state, symbol, next_state, symbol, move)

    def build(self, start_state: str) -> RawTM:
        return RawTM(self.prog, start_state=start_state, halt_state=self.halt_state, alphabet=self.alphabet, blank=self.blank)


def run_raw_tm(tm: RawTM, tape: dict[int, str], *, head: int = 0, state: str | None = None, max_steps: int = 100):
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


__all__ = ["L", "R", "S", "RawTM", "TMBuilder", "run_raw_tm"]
