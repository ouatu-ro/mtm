"""Typed debugger queries over in-memory trace facts."""

from __future__ import annotations

from dataclasses import dataclass

from .facts import SemanticFact, SnapshotFact, SourceFact, TapeWindowFact, TraceFacts, TransitionFact


@dataclass(frozen=True)
class SnapshotRow:
    run_status: str
    raw: int
    max_raw: int
    hist_current: int
    hist_last: int
    state: str
    head: int
    read_symbol: str


@dataclass(frozen=True)
class SourceRow:
    mapped: bool
    block: str | None
    instr: str | None
    routine: str | None
    op: int | None
    opcode: str | None
    args: tuple[str, ...]
    explanation: str | None


@dataclass(frozen=True)
class TransitionRow:
    present: bool
    state: str | None
    read_symbol: str | None
    write_symbol: str | None
    move: int | None
    next_state: str | None


@dataclass(frozen=True)
class StatusRow:
    snapshot: SnapshotRow
    source: SourceRow


@dataclass(frozen=True)
class WhereRow:
    source: SourceRow
    next_row: TransitionRow


@dataclass(frozen=True)
class ViewRow:
    status: StatusRow
    next_row: TransitionRow
    last_row: TransitionRow
    raw_tape: TapeWindowFact
    semantic: SemanticFact


@dataclass(frozen=True)
class ActionRow:
    verb: str
    boundary: str
    status: str
    raw_delta: int
    count_completed: int
    count_requested: int
    snapshot: SnapshotRow
    source: SourceRow
    next_row: TransitionRow


class DebuggerQueries:
    """Read-model queries over a materialized trace fact set."""

    def __init__(self, facts: TraceFacts, *, max_raw: int) -> None:
        self.facts = facts
        self.max_raw = max_raw

    def status(self) -> StatusRow:
        return StatusRow(
            snapshot=self._snapshot_row(self.facts.current_snapshot),
            source=self._source_row(self.facts.display_source),
        )

    def where(self) -> WhereRow:
        return WhereRow(
            source=self._source_row(self.facts.display_source),
            next_row=self._transition_row(self.facts.next_transition),
        )

    def view(self) -> ViewRow:
        return ViewRow(
            status=self.status(),
            next_row=self._transition_row(self.facts.next_transition),
            last_row=self._transition_row(self.facts.last_transition),
            raw_tape=self.facts.raw_tape,
            semantic=self.facts.semantic,
        )

    def action(
        self,
        *,
        verb: str,
        boundary: str,
        status: str,
        raw_delta: int,
        count_completed: int,
        count_requested: int,
    ) -> ActionRow:
        status_row = self.status()
        return ActionRow(
            verb=verb,
            boundary=boundary,
            status=status,
            raw_delta=raw_delta,
            count_completed=count_completed,
            count_requested=count_requested,
            snapshot=status_row.snapshot,
            source=status_row.source,
            next_row=self._transition_row(self.facts.next_transition),
        )

    def next_boundary(self, kind: str, after: int) -> int | None:
        return self._find_boundary(kind, start=max(after + 1, 0), stop=self.facts.latest_history_index + 1, step=1)

    def previous_boundary(self, kind: str, before: int) -> int | None:
        return self._find_boundary(kind, start=min(before - 1, self.facts.latest_history_index), stop=-1, step=-1)

    def _find_boundary(self, kind: str, *, start: int, stop: int, step: int) -> int | None:
        previous = self._boundary_key(self._display_source_for_cursor(self.facts.cursor), kind)
        for cursor in range(start, stop, step):
            current = self._boundary_key(self._display_source_for_cursor(cursor), kind)
            if current is None:
                continue
            if current != previous:
                return cursor
        return None

    def _display_source_for_cursor(self, cursor: int) -> SourceRow:
        current = self.facts.runner._snapshots[cursor]
        key = None if current.state == self.facts.runner.program.halt_state else (
            current.state,
            current.tape.get(current.head, self.facts.runner.program.blank),
        )
        source = None if key is None or self.facts.runner.source_map is None else self.facts.runner.source_map.lookup(*key)
        if source is None and cursor > 0:
            source = self.facts.runner._history[cursor - 1].source
        return self._source_row(self.facts._source_fact(current.steps, source))

    def _boundary_key(self, source: SourceRow, kind: str):
        if not source.mapped:
            return None
        if kind == "routine":
            return source.routine
        if kind == "instruction":
            return (source.block, source.instr)
        if kind == "block":
            return source.block
        if kind == "source":
            return source.block == self.facts.runner.source_step_block_label
        return None

    def _snapshot_row(self, fact: SnapshotFact) -> SnapshotRow:
        return SnapshotRow(
            run_status=self.facts.run_status,
            raw=fact.step,
            max_raw=self.max_raw,
            hist_current=self.facts.cursor,
            hist_last=self.facts.latest_history_index,
            state=fact.state,
            head=fact.head,
            read_symbol=fact.read_symbol,
        )

    @staticmethod
    def _source_row(fact: SourceFact) -> SourceRow:
        routine = None
        if fact.routine_name is not None:
            routine = fact.routine_name if fact.routine_index is None else f"{fact.routine_index}:{fact.routine_name}"
        return SourceRow(
            mapped=fact.mapped,
            block=fact.block,
            instr=fact.instr,
            routine=routine,
            op=fact.op,
            opcode=fact.opcode,
            args=fact.args,
            explanation=fact.explanation,
        )

    @staticmethod
    def _transition_row(fact: TransitionFact) -> TransitionRow:
        return TransitionRow(
            present=fact.present,
            state=fact.state,
            read_symbol=fact.read_symbol,
            write_symbol=fact.write_symbol,
            move=fact.move,
            next_state=fact.next_state,
        )


__all__ = [
    "ActionRow",
    "DebuggerQueries",
    "SnapshotRow",
    "SourceRow",
    "StatusRow",
    "TransitionRow",
    "ViewRow",
    "WhereRow",
]
