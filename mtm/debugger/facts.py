"""In-memory debugger facts built from a raw trace runner.

This module turns the runner's live trace state into small, stable records that
the query and presentation layers can read without reaching back into runner
internals. The goal is to make debugger output easy to explain, test, and
render.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..lowering.source_map import RawTransitionSource
from ..semantic_objects import DecodedUTMView
from ..source_encoding import Encoding
from .instructions import explain_meta_instruction
from .trace import RawTraceRunner, RawTraceSnapshot


@dataclass(frozen=True)
class SnapshotFact:
    """One raw-history snapshot, reduced to the fields the debugger displays."""
    step: int
    state: str
    head: int
    read_symbol: str


@dataclass(frozen=True)
class EventFact:
    """One executed raw transition row from the runner history."""
    step: int
    state: str
    read_symbol: str
    write_symbol: str
    move: int
    next_state: str


@dataclass(frozen=True)
class SourceFact:
    """The source-level location and decoded instruction for one raw row."""
    step: int
    block: str | None
    instr: str | None
    routine_index: int | None
    routine_name: str | None
    op: int | None
    instruction_text: str | None
    explanation: str | None
    opcode: str | None
    args: tuple[str, ...]
    mapped: bool


@dataclass(frozen=True)
class TransitionFact:
    """The raw transition row that will execute next, if one exists."""
    present: bool
    state: str | None
    read_symbol: str | None
    write_symbol: str | None
    move: int | None
    next_state: str | None


@dataclass(frozen=True)
class TapeCellFact:
    """One address/symbol pair from a debugger tape window."""
    address: int
    symbol: str


@dataclass(frozen=True)
class TapeWindowFact:
    """A small tape slice centered on the current head position."""
    head: int
    cells: tuple[TapeCellFact, ...]


@dataclass(frozen=True)
class SemanticFact:
    """Decoded universal-machine state for the simulated source machine."""
    status: str
    state: str | None = None
    head: int | None = None
    symbol: str | None = None
    tape: TapeWindowFact | None = None
    registers: tuple[tuple[str, str], ...] = ()
    decode_error: str | None = None


class TraceFacts:
    """Materialize runner trace state into query-friendly fact records.

    The query layer reads these cached records instead of walking the runner
    history directly. Rebuilding is explicit so callers can refresh after the
    runner advances, changes encoding, or changes tape window sizes.
    """

    def __init__(
        self,
        runner: RawTraceRunner,
        *,
        encoding: Encoding | None = None,
        raw_window: int = 2,
        semantic_window: int = 2,
    ) -> None:
        self.runner = runner
        self.encoding = encoding
        self.raw_window = raw_window
        self.semantic_window = semantic_window
        self.rebuild_from_trace()

    def rebuild_from_trace(self) -> None:
        """Refresh every derived fact from the runner's current trace state."""
        self.cursor = self.runner.history_cursor
        self.latest_history_index = self.runner.latest_history_index
        self.run_status = self.runner.run_status
        self.snapshots = tuple(self._snapshot_fact(snapshot) for snapshot in self.runner._snapshots)
        self.events = tuple(
            EventFact(
                step=transition.step,
                state=transition.state,
                read_symbol=transition.read_symbol,
                write_symbol=transition.write_symbol,
                move=transition.move,
                next_state=transition.next_state,
            )
            for transition in self.runner._history
        )
        self.current_snapshot = self._snapshot_fact(self.runner.current)
        self.last_event = None if self.runner.last_transition is None else EventFact(
            step=self.runner.last_transition.step,
            state=self.runner.last_transition.state,
            read_symbol=self.runner.last_transition.read_symbol,
            write_symbol=self.runner.last_transition.write_symbol,
            move=self.runner.last_transition.move,
            next_state=self.runner.last_transition.next_state,
        )
        self.current_source = self._source_fact(self.runner.current.steps, self.runner.current_transition_source)
        self.last_source = self._source_fact(
            self.runner.current.steps,
            self.runner.last_transition_source,
        )
        display_source = self.runner.current_transition_source or self.runner.last_transition_source
        self.display_source = self._source_fact(self.runner.current.steps, display_source)
        self.next_transition = self._transition_fact(self.runner.current_transition_key, self.runner.current_transition)
        self.last_transition = self._transition_fact_from_event(self.last_event)
        self.raw_tape = self._tape_window(self.runner.current)
        self.semantic = self._semantic_fact()

    def set_encoding(self, encoding: Encoding | None) -> None:
        """Change the semantic decoder and immediately rebuild derived facts."""
        self.encoding = encoding
        self.rebuild_from_trace()

    def set_windows(self, *, raw_window: int | None = None, semantic_window: int | None = None) -> None:
        """Adjust the raw or semantic tape window sizes and rebuild facts."""
        if raw_window is not None:
            self.raw_window = raw_window
        if semantic_window is not None:
            self.semantic_window = semantic_window
        self.rebuild_from_trace()

    def _snapshot_fact(self, snapshot: RawTraceSnapshot) -> SnapshotFact:
        return SnapshotFact(
            step=snapshot.steps,
            state=snapshot.state,
            head=snapshot.head,
            read_symbol=snapshot.tape.get(snapshot.head, self.runner.program.blank),
        )

    def _source_fact(self, step: int, source: RawTransitionSource | None) -> SourceFact:
        if source is None:
            return SourceFact(
                step=step, block=None, instr=None, routine_index=None, routine_name=None, op=None,
                instruction_text=None, explanation=None, opcode=None, args=(), mapped=False,
            )
        opcode, args = _split_instruction_text(source.instruction_text)
        return SourceFact(
            step=step, block=source.block_label,
            instr="setup" if source.instruction_index is None else str(source.instruction_index),
            routine_index=source.routine_index, routine_name=source.routine_name, op=source.op_index,
            instruction_text=source.instruction_text, explanation=explain_meta_instruction(source.instruction),
            opcode=opcode, args=args, mapped=True,
        )

    @staticmethod
    def _transition_fact(key, row) -> TransitionFact:
        if key is None or row is None:
            return TransitionFact(False, None, None, None, None, None)
        state, read_symbol = key
        next_state, write_symbol, move = row
        return TransitionFact(
            present=True, state=state, read_symbol=read_symbol,
            write_symbol=write_symbol, move=move, next_state=next_state,
        )

    @staticmethod
    def _transition_fact_from_event(event: EventFact | None) -> TransitionFact:
        if event is None:
            return TransitionFact(False, None, None, None, None, None)
        return TransitionFact(
            present=True, state=event.state, read_symbol=event.read_symbol,
            write_symbol=event.write_symbol, move=event.move, next_state=event.next_state,
        )

    def _tape_window(self, snapshot: RawTraceSnapshot) -> TapeWindowFact:
        cells = tuple(
            TapeCellFact(address=address, symbol=snapshot.tape.get(address, self.runner.program.blank))
            for address in range(snapshot.head - self.raw_window, snapshot.head + self.raw_window + 1)
        )
        return TapeWindowFact(head=snapshot.head, cells=cells)

    def _semantic_fact(self) -> SemanticFact:
        if self.encoding is None:
            return SemanticFact(status="unavailable")
        decoded_view: DecodedUTMView | None = None
        decode_error: str | None = None
        try:
            decoded_view = self.runner.current_view(encoding=self.encoding).decoded_view
        except Exception as exc:  # pragma: no cover - defensive
            decode_error = f"{type(exc).__name__}: {exc}"

        if decoded_view is None:
            view = self.runner.current_view(encoding=self.encoding)
            if view.decode_error is not None:
                return SemanticFact(status="error", decode_error=view.decode_error)
            if decode_error is not None:
                return SemanticFact(status="error", decode_error=decode_error)
            return SemanticFact(status="unavailable")

        head = decoded_view.simulated_tape.head
        cells = {
            **{index - len(decoded_view.simulated_tape.left_band): symbol for index, symbol in enumerate(decoded_view.simulated_tape.left_band)},
            **{index: symbol for index, symbol in enumerate(decoded_view.simulated_tape.right_band)},
        }
        tape = TapeWindowFact(
            head=head,
            cells=tuple(
                TapeCellFact(address=address, symbol=cells.get(address, decoded_view.simulated_tape.blank))
                for address in range(head - self.semantic_window, head + self.semantic_window + 1)
            ),
        )
        registers = decoded_view.registers
        return SemanticFact(
            status="available", state=decoded_view.current_state, head=head,
            symbol=cells.get(head, decoded_view.simulated_tape.blank), tape=tape,
            registers=(
                ("cur", registers.cur_state), ("read", registers.cur_symbol), ("write", registers.write_symbol),
                ("next", registers.next_state), ("move", _format_move(registers.move_dir)),
                ("cmp", registers.cmp_flag), ("tmp", "".join(registers.tmp_bits) or "-"),
            ),
        )


def _split_instruction_text(text: str | None) -> tuple[str | None, tuple[str, ...]]:
    if text is None:
        return None, ()
    parts = text.split()
    if not parts:
        return None, ()
    return parts[0], tuple(parts[1:])


def _format_move(move: int) -> str:
    if move < 0:
        return "L"
    if move > 0:
        return "R"
    return "S"


__all__ = [
    "EventFact",
    "SemanticFact",
    "SnapshotFact",
    "SourceFact",
    "TapeCellFact",
    "TapeWindowFact",
    "TraceFacts",
    "TransitionFact",
]
