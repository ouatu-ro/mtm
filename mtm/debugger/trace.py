"""Single-step tracing for raw transition-machine programs."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..lowering.source_map import RawTransitionSource, TransitionSourceMap
from ..raw_transition_tm import TMTransitionProgram, Transition, TransitionKey


@dataclass(frozen=True)
class RawTraceSnapshot:
    """One immutable raw-machine configuration."""

    tape: Mapping[int, str]
    head: int
    state: str
    steps: int

    def tape_dict(self) -> dict[int, str]:
        """Return a mutable copy of this snapshot's sparse tape."""

        return dict(self.tape)


@dataclass(frozen=True)
class RawTraceTransition:
    """One executed raw transition plus optional source metadata."""

    step: int
    state: str
    read_symbol: str
    next_state: str
    write_symbol: str
    move: int
    source: RawTransitionSource | None = None

    @property
    def key(self) -> TransitionKey:
        """Return the concrete transition-table key for this row."""

        return (self.state, self.read_symbol)


@dataclass(frozen=True)
class RawTraceStepResult:
    """Result of one `RawTraceRunner.step()` call."""

    status: str
    snapshot: RawTraceSnapshot
    transition: RawTraceTransition | None


@dataclass(frozen=True)
class RawTraceRunResult:
    """Result of running until halt, stuck, or fuel exhaustion."""

    status: str
    snapshot: RawTraceSnapshot
    steps_executed: int


class RawTraceRunner:
    """Step a raw transition program forward and backward using full snapshots."""

    def __init__(
        self,
        program: TMTransitionProgram,
        tape: dict[int, str],
        *,
        head: int = 0,
        state: str | None = None,
        source_map: TransitionSourceMap | None = None,
    ) -> None:
        self.program = program
        self.source_map = source_map
        start_state = program.start_state if state is None else state
        self._snapshots = [self._freeze_snapshot(dict(tape), head=head, state=start_state, steps=0)]
        self._history: list[RawTraceTransition] = []

    @property
    def current(self) -> RawTraceSnapshot:
        """Return the active machine snapshot."""

        return self._snapshots[-1]

    @property
    def last_transition(self) -> RawTraceTransition | None:
        """Return the most recently executed transition, if any."""

        if not self._history:
            return None
        return self._history[-1]

    @property
    def current_read_symbol(self) -> str:
        """Return the symbol under the head in the current snapshot."""

        snapshot = self.current
        return snapshot.tape.get(snapshot.head, self.program.blank)

    @property
    def current_transition_key(self) -> TransitionKey | None:
        """Return the raw row the runner would execute next, if any."""

        if self.is_halted:
            return None
        return (self.current.state, self.current_read_symbol)

    @property
    def current_transition(self) -> Transition | None:
        """Return the next raw transition row, if one exists."""

        key = self.current_transition_key
        if key is None:
            return None
        return self.program.prog.get(key)

    @property
    def current_transition_source(self) -> RawTransitionSource | None:
        """Return source metadata for the next row, if one exists."""

        key = self.current_transition_key
        if key is None or self.source_map is None:
            return None
        return self.source_map.lookup(*key)

    @property
    def last_transition_source(self) -> RawTransitionSource | None:
        """Return source metadata for the last executed row, if any."""

        transition = self.last_transition
        if transition is None:
            return None
        return transition.source

    @property
    def is_halted(self) -> bool:
        """Return whether the current state is the machine halt state."""

        return self.current.state == self.program.halt_state

    @property
    def is_stuck(self) -> bool:
        """Return whether execution cannot proceed from the current snapshot."""

        return not self.is_halted and self.current_transition is None

    def step(self) -> RawTraceStepResult:
        """Execute one raw transition if possible."""

        if self.is_halted:
            return RawTraceStepResult(status="halted", snapshot=self.current, transition=None)

        snapshot = self.current
        read_symbol = self.current_read_symbol
        transition = self.program.prog.get((snapshot.state, read_symbol))
        if transition is None:
            return RawTraceStepResult(status="stuck", snapshot=snapshot, transition=None)

        next_state, write_symbol, move = transition
        next_tape = snapshot.tape_dict()
        next_tape[snapshot.head] = write_symbol
        executed = RawTraceTransition(
            step=snapshot.steps + 1,
            state=snapshot.state,
            read_symbol=read_symbol,
            next_state=next_state,
            write_symbol=write_symbol,
            move=move,
            source=self._lookup_source(snapshot.state, read_symbol),
        )
        next_snapshot = self._freeze_snapshot(
            next_tape,
            head=snapshot.head + move,
            state=next_state,
            steps=snapshot.steps + 1,
        )
        self._history.append(executed)
        self._snapshots.append(next_snapshot)
        return RawTraceStepResult(status="stepped", snapshot=next_snapshot, transition=executed)

    def back(self) -> bool:
        """Restore the previous snapshot if history exists."""

        if len(self._snapshots) == 1:
            return False
        self._snapshots.pop()
        self._history.pop()
        return True

    def run(self, max_steps: int) -> RawTraceRunResult:
        """Run until halt, stuck, or the step budget is exhausted."""

        if max_steps < 0:
            raise ValueError("max_steps must be non-negative")

        start_steps = self.current.steps
        steps_left = max_steps
        while steps_left > 0:
            step_result = self.step()
            if step_result.status != "stepped":
                return RawTraceRunResult(
                    status=step_result.status,
                    snapshot=step_result.snapshot,
                    steps_executed=self.current.steps - start_steps,
                )
            steps_left -= 1

        if self.is_halted:
            status = "halted"
        elif self.is_stuck:
            status = "stuck"
        else:
            status = "fuel_exhausted"
        return RawTraceRunResult(status=status, snapshot=self.current, steps_executed=self.current.steps - start_steps)

    def _freeze_snapshot(self, tape: dict[int, str], *, head: int, state: str, steps: int) -> RawTraceSnapshot:
        return RawTraceSnapshot(tape=MappingProxyType(dict(tape)), head=head, state=state, steps=steps)

    def _lookup_source(self, state: str, read_symbol: str) -> RawTransitionSource | None:
        if self.source_map is None:
            return None
        return self.source_map.lookup(state, read_symbol)


__all__ = [
    "RawTraceRunResult",
    "RawTraceRunner",
    "RawTraceSnapshot",
    "RawTraceStepResult",
    "RawTraceTransition",
]
