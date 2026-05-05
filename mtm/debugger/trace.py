"""Reversible tracing for raw transition-machine programs.

The core object is ``RawTraceRunner``. It always executes concrete raw TM rows,
and it can optionally layer on:

- lowering source metadata for "where did this row come from?"
- grouped stepping across routine/instruction/block/source-step boundaries
- semantic decode of an encoded UTM band for teaching-facing inspection
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping

from ..lowering.source_map import RawTransitionSource, TransitionSourceMap
from ..raw_transition_tm import TMTransitionProgram, Transition, TransitionKey
from ..semantic_objects import DecodedBandView, decoded_view_from_encoded_band
from ..source_encoding import Encoding
from ..utm_band_layout import EncodedBand


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


@dataclass(frozen=True)
class RawTraceGroupStepResult:
    """Result of stepping across one source-level boundary."""

    status: str
    snapshot: RawTraceSnapshot
    raw_steps: int


@dataclass(frozen=True)
class RawTraceView:
    """Projection of the runner's current state for teaching-facing inspection."""

    snapshot: RawTraceSnapshot
    next_raw_transition_key: TransitionKey | None
    next_raw_transition_row: Transition | None
    next_raw_transition_source: RawTransitionSource | None
    last_transition: RawTraceTransition | None
    last_transition_source: RawTransitionSource | None
    decoded_view: DecodedBandView | None
    decode_error: str | None


class RawTraceRunner:
    """Step a raw transition program forward and backward using full snapshots."""

    DEFAULT_SOURCE_STEP_BLOCK_LABEL = "START_STEP"

    def __init__(
        self,
        program: TMTransitionProgram,
        tape: dict[int, str],
        *,
        head: int = 0,
        state: str | None = None,
        source_map: TransitionSourceMap | None = None,
        source_step_block_label: str = DEFAULT_SOURCE_STEP_BLOCK_LABEL,
    ) -> None:
        self.program = program
        self.source_map = source_map
        self.source_step_block_label = source_step_block_label
        start_state = program.start_state if state is None else state
        self._snapshots = [self._freeze_snapshot(dict(tape), head=head, state=start_state, steps=0)]
        self._history: list[RawTraceTransition] = []
        self._cursor = 0

    @property
    def current(self) -> RawTraceSnapshot:
        """Return the active machine snapshot."""

        return self._snapshots[self._cursor]

    @property
    def history_cursor(self) -> int:
        """Return the active snapshot index in execution history."""

        return self._cursor

    @property
    def latest_history_index(self) -> int:
        """Return the newest stored snapshot index."""

        return len(self._snapshots) - 1

    @property
    def last_transition(self) -> RawTraceTransition | None:
        """Return the most recently executed transition, if any."""

        if self._cursor == 0:
            return None
        return self._history[self._cursor - 1]

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

    @property
    def run_status(self) -> str:
        """Return the runner's current execution status."""

        if self.is_halted:
            return "halted"
        if self.is_stuck:
            return "stuck"
        return "running"

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
        if self._cursor < self.latest_history_index:
            self._snapshots = self._snapshots[:self._cursor + 1]
            self._history = self._history[:self._cursor]
        self._history.append(executed)
        self._snapshots.append(next_snapshot)
        self._cursor += 1
        return RawTraceStepResult(status="stepped", snapshot=next_snapshot, transition=executed)

    def back(self) -> bool:
        """Restore the previous snapshot if history exists."""

        if self._cursor == 0:
            return False
        self._cursor -= 1
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

    def step_to_next_routine(self, *, max_raw: int | None = None) -> RawTraceGroupStepResult:
        """Advance until the next routine boundary."""

        return self._step_to_next_group(lambda source: source.routine_index, max_raw=max_raw)

    def step_to_next_instruction(self, *, max_raw: int | None = None) -> RawTraceGroupStepResult:
        """Advance until the next instruction boundary."""

        return self._step_to_next_group(lambda source: (source.block_label, source.instruction_index), max_raw=max_raw)

    def step_to_next_block(self, *, max_raw: int | None = None) -> RawTraceGroupStepResult:
        """Advance until the next block boundary."""

        return self._step_to_next_group(lambda source: source.block_label, max_raw=max_raw)

    def step_to_next_source_step(self, *, max_raw: int | None = None) -> RawTraceGroupStepResult:
        """Advance until the next universal-machine source-step boundary."""

        return self._step_to_next_source_step_boundary(max_raw=max_raw)

    def back_to_previous_routine(self) -> RawTraceGroupStepResult:
        """Rewind to the previous routine boundary."""

        return self._back_to_previous_group(lambda source: source.routine_index)

    def back_to_previous_instruction(self) -> RawTraceGroupStepResult:
        """Rewind to the previous instruction boundary."""

        return self._back_to_previous_group(lambda source: (source.block_label, source.instruction_index))

    def back_to_previous_block(self) -> RawTraceGroupStepResult:
        """Rewind to the previous block boundary."""

        return self._back_to_previous_group(lambda source: source.block_label)

    def back_to_previous_source_step(self) -> RawTraceGroupStepResult:
        """Rewind to the previous universal-machine source-step boundary."""

        return self._back_to_previous_source_step_boundary()

    def current_view(self, *, encoding: Encoding | None = None) -> RawTraceView:
        """Return the current raw view plus an optional semantic decode."""

        decoded_view = None
        decode_error = None
        if encoding is not None:
            try:
                band = EncodedBand.from_runtime_tape(encoding, self.current.tape_dict())
                decoded_view = decoded_view_from_encoded_band(band)
            except Exception as exc:  # pragma: no cover - exercised through public fields
                decode_error = f"{type(exc).__name__}: {exc}"
        return RawTraceView(
            snapshot=self.current,
            next_raw_transition_key=self.current_transition_key,
            next_raw_transition_row=self.current_transition,
            next_raw_transition_source=self.current_transition_source,
            last_transition=self.last_transition,
            last_transition_source=self.last_transition_source,
            decoded_view=decoded_view,
            decode_error=decode_error,
        )

    def _freeze_snapshot(self, tape: dict[int, str], *, head: int, state: str, steps: int) -> RawTraceSnapshot:
        return RawTraceSnapshot(tape=MappingProxyType(dict(tape)), head=head, state=state, steps=steps)

    def _lookup_source(self, state: str, read_symbol: str) -> RawTransitionSource | None:
        if self.source_map is None:
            return None
        return self.source_map.lookup(state, read_symbol)

    def _step_to_next_group(
        self,
        group_for_source: Callable[[RawTransitionSource], object],
        *,
        max_raw: int | None = None,
    ) -> RawTraceGroupStepResult:
        if max_raw is not None and max_raw <= 0:
            raise ValueError("max_raw must be positive")
        source = self.current_transition_source
        if source is None:
            return RawTraceGroupStepResult(
                status=self.run_status if self.run_status != "running" else "unmapped",
                snapshot=self.current,
                raw_steps=0,
            )
        start_group = group_for_source(source)
        raw_steps = 0
        while True:
            if max_raw is not None and raw_steps >= max_raw:
                return RawTraceGroupStepResult(status="max_raw", snapshot=self.current, raw_steps=raw_steps)
            step_result = self.step()
            if step_result.status != "stepped":
                return RawTraceGroupStepResult(
                    status=step_result.status,
                    snapshot=step_result.snapshot,
                    raw_steps=raw_steps,
                )
            raw_steps += 1
            source = self.current_transition_source
            if source is None:
                return RawTraceGroupStepResult(
                    status=self.run_status if self.run_status != "running" else "unmapped",
                    snapshot=self.current,
                    raw_steps=raw_steps,
                )
            if group_for_source(source) != start_group:
                return RawTraceGroupStepResult(status="stepped", snapshot=self.current, raw_steps=raw_steps)

    def _back_to_previous_group(self, group_for_source: Callable[[RawTransitionSource], object]) -> RawTraceGroupStepResult:
        segment_starts = self._find_group_segment_starts(group_for_source)
        if segment_starts is None:
            return RawTraceGroupStepResult(status="unmapped", snapshot=self.current, raw_steps=0)
        if len(segment_starts) < 2:
            return RawTraceGroupStepResult(status="at_start", snapshot=self.current, raw_steps=0)
        target_index = segment_starts[-2]
        raw_steps = self._cursor - target_index
        self._cursor = target_index
        return RawTraceGroupStepResult(status="stepped", snapshot=self.current, raw_steps=raw_steps)

    def _step_to_next_source_step_boundary(self, *, max_raw: int | None = None) -> RawTraceGroupStepResult:
        if max_raw is not None and max_raw <= 0:
            raise ValueError("max_raw must be positive")
        source = self.current_transition_source
        if source is None:
            return RawTraceGroupStepResult(
                status=self.run_status if self.run_status != "running" else "unmapped",
                snapshot=self.current,
                raw_steps=0,
            )

        left_current_boundary = source.block_label != self.source_step_block_label
        raw_steps = 0
        while True:
            if max_raw is not None and raw_steps >= max_raw:
                return RawTraceGroupStepResult(status="max_raw", snapshot=self.current, raw_steps=raw_steps)
            step_result = self.step()
            if step_result.status != "stepped":
                return RawTraceGroupStepResult(
                    status=step_result.status,
                    snapshot=step_result.snapshot,
                    raw_steps=raw_steps,
                )
            raw_steps += 1
            source = self.current_transition_source
            if source is None:
                return RawTraceGroupStepResult(
                    status=self.run_status if self.run_status != "running" else "unmapped",
                    snapshot=self.current,
                    raw_steps=raw_steps,
                )
            if source.block_label != self.source_step_block_label:
                left_current_boundary = True
                continue
            if left_current_boundary:
                return RawTraceGroupStepResult(status="stepped", snapshot=self.current, raw_steps=raw_steps)

    def _back_to_previous_source_step_boundary(self) -> RawTraceGroupStepResult:
        segment_starts = self._find_source_step_segment_starts()
        if segment_starts is None:
            return RawTraceGroupStepResult(status="unmapped", snapshot=self.current, raw_steps=0)
        if len(segment_starts) < 2:
            return RawTraceGroupStepResult(status="at_start", snapshot=self.current, raw_steps=0)
        target_index = segment_starts[-2]
        raw_steps = self._cursor - target_index
        self._cursor = target_index
        return RawTraceGroupStepResult(status="stepped", snapshot=self.current, raw_steps=raw_steps)

    def _source_for_previous_snapshot(self) -> RawTransitionSource | None:
        return self._source_for_snapshot_index(-2)

    def _source_for_snapshot_index(self, index: int) -> RawTransitionSource | None:
        try:
            snapshot = self._snapshots[self._resolve_snapshot_index(index)]
        except IndexError:
            return None
        return self._lookup_source(snapshot.state, self._read_symbol_for_snapshot(snapshot))

    def _resolve_snapshot_index(self, index: int) -> int:
        if index < 0:
            resolved = self._cursor + 1 + index
            if resolved < 0:
                raise IndexError(index)
            return resolved
        return index

    def _find_group_segment_starts(
        self,
        group_for_source: Callable[[RawTransitionSource], object],
    ) -> list[int] | None:
        segment_starts: list[int] = []
        for snapshot_index in range(self._cursor + 1):
            source = self._source_for_snapshot_index(snapshot_index)
            if source is None:
                if self._is_terminal_cursor_snapshot(snapshot_index):
                    continue
                return None
            previous_source = None if snapshot_index == 0 else self._source_for_snapshot_index(snapshot_index - 1)
            if snapshot_index == 0:
                segment_starts.append(snapshot_index)
                continue
            if previous_source is None:
                return None
            if group_for_source(previous_source) != group_for_source(source):
                segment_starts.append(snapshot_index)
        return segment_starts

    def _find_source_step_segment_starts(self) -> list[int] | None:
        segment_starts: list[int] = []
        for snapshot_index in range(self._cursor + 1):
            source = self._source_for_snapshot_index(snapshot_index)
            if source is None:
                if self._is_terminal_cursor_snapshot(snapshot_index):
                    continue
                return None
            if source.block_label != self.source_step_block_label:
                continue
            previous_source = None if snapshot_index == 0 else self._source_for_snapshot_index(snapshot_index - 1)
            if snapshot_index == 0:
                segment_starts.append(snapshot_index)
                continue
            if previous_source is None:
                return None
            if previous_source.block_label != self.source_step_block_label:
                segment_starts.append(snapshot_index)
        return segment_starts

    def _is_terminal_cursor_snapshot(self, snapshot_index: int) -> bool:
        return snapshot_index == self._cursor and self.run_status != "running"

    def _read_symbol_for_snapshot(self, snapshot: RawTraceSnapshot) -> str:
        return snapshot.tape.get(snapshot.head, self.program.blank)


__all__ = [
    "RawTraceGroupStepResult",
    "RawTraceRunResult",
    "RawTraceRunner",
    "RawTraceSnapshot",
    "RawTraceStepResult",
    "RawTraceTransition",
    "RawTraceView",
]
