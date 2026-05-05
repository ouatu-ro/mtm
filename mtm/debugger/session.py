"""Session-layer debugger formatting and command dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..lowering.source_map import RawTransitionSource
from ..source_encoding import Encoding
from .render import _format_decoded_view, _format_last_transition, _format_move, _format_sparse_tape, _format_transition
from .trace import RawTraceRunner, RawTraceSnapshot

Boundary = Literal["raw", "routine", "instruction", "block", "source"]
ActionStatus = Literal["stepped", "rewound", "halted", "stuck", "max_raw", "unmapped", "at_start"]


@dataclass(frozen=True)
class DebuggerActionResult:
    """User-facing result for one debugger action."""

    boundary: Boundary
    status: ActionStatus
    raw_steps: int
    snapshot: RawTraceSnapshot
    source: RawTransitionSource | None


class DebuggerSession:
    """User-facing debugger commands layered over a raw trace runner."""

    DEFAULT_MAX_RAW = 100_000

    def __init__(
        self,
        runner: RawTraceRunner,
        *,
        encoding: Encoding | None = None,
        max_raw: int = DEFAULT_MAX_RAW,
        raw_window: int = 2,
        semantic_window: int = 2,
    ) -> None:
        if max_raw <= 0:
            raise ValueError("max_raw must be positive")
        self.runner = runner
        self.encoding = encoding
        self.max_raw = max_raw
        self.raw_window = raw_window
        self.semantic_window = semantic_window

    def status_text(self) -> str:
        """Return the compact debugger status view."""

        lines = [
            self._format_status_line(),
            self._format_snapshot_line(self.runner.current, include_raw_step=False),
        ]
        source = self._display_source()
        lines.append(self._format_where_header(source))
        instruction_line = self._format_instruction_line(source)
        if instruction_line is not None:
            lines.append(instruction_line)
        return "\n".join(lines)

    def where_text(self) -> str:
        """Return the current lowered source location view."""

        source = self._display_source()
        if source is None:
            return "where: <unmapped>"
        lines = [
            self._format_where_header(source),
            self._format_source_row(source),
        ]
        instruction_line = self._format_instruction_line(source)
        if instruction_line is not None:
            lines.append(instruction_line)
        return "\n".join(lines)

    def view_text(self) -> str:
        """Return the heavier debugger trace view."""

        view = self.runner.current_view(encoding=self.encoding)
        lines = [
            self._format_status_line(),
            self._format_snapshot_line(view.snapshot, include_raw_step=True),
            f"raw tape: {_format_sparse_tape(view.snapshot.tape, head=view.snapshot.head, radius=self.raw_window, blank_symbol=self.runner.program.blank)}",
        ]
        if view.next_raw_transition_key is None or view.next_raw_transition_row is None:
            lines.append("next raw: <none>")
        else:
            lines.append(f"next raw: {_format_transition(view.next_raw_transition_key, view.next_raw_transition_row)}")
        if view.last_transition is None:
            lines.append("last raw: <none>")
        else:
            lines.append(f"last raw: {_format_last_transition(view.last_transition)}")

        source = view.next_raw_transition_source or view.last_transition_source
        lines.append(self.where_text() if source is not None else "where: <unmapped>")
        lines.extend(self._format_semantic_lines(view.decoded_view, view.decode_error))
        return "\n".join(lines)

    def step(self, boundary: Boundary) -> DebuggerActionResult:
        """Execute one debugger step command."""

        if boundary == "raw":
            step_result = self.runner.step()
            return DebuggerActionResult(
                boundary=boundary,
                status=step_result.status,
                raw_steps=1 if step_result.status == "stepped" else 0,
                snapshot=step_result.snapshot,
                source=self._display_source(),
            )

        result = self._group_step(boundary)
        return DebuggerActionResult(
            boundary=boundary,
            status=result.status,
            raw_steps=result.raw_steps,
            snapshot=result.snapshot,
            source=self._display_source(),
        )

    def step_text(self, boundary: Boundary) -> str:
        """Execute and format one debugger step command."""

        return self.format_action_text("step", self.step(boundary))

    def back(self, boundary: Boundary) -> DebuggerActionResult:
        """Execute one debugger rewind command."""

        if boundary == "raw":
            rewound = self.runner.back()
            return DebuggerActionResult(
                boundary=boundary,
                status="rewound" if rewound else "at_start",
                raw_steps=1 if rewound else 0,
                snapshot=self.runner.current,
                source=self._display_source(),
            )

        result = self._group_back(boundary)
        status: ActionStatus = "rewound" if result.status == "stepped" else result.status
        return DebuggerActionResult(
            boundary=boundary,
            status=status,
            raw_steps=result.raw_steps,
            snapshot=result.snapshot,
            source=self._display_source(),
        )

    def back_text(self, boundary: Boundary) -> str:
        """Execute and format one debugger rewind command."""

        return self.format_action_text("back", self.back(boundary))

    def format_action_text(self, verb: Literal["step", "back"], result: DebuggerActionResult) -> str:
        """Format a debugger action result for REPL output."""

        lines = [
            f"{verb} {result.boundary}: status={result.status} raw_steps={result.raw_steps}",
            self._format_snapshot_line(result.snapshot, include_raw_step=True),
        ]
        lines.append(self._format_where_header(result.source))
        row_line = self._format_action_row()
        if row_line is not None:
            lines.append(row_line)
        instruction_line = self._format_instruction_line(result.source)
        if instruction_line is not None:
            lines.append(instruction_line)
        return "\n".join(lines)

    def set_max_raw(self, value: int) -> str:
        """Update the grouped-step guard."""

        if value <= 0:
            raise ValueError("max_raw must be positive")
        self.max_raw = value
        return f"max_raw: {self.max_raw}"

    def _group_step(self, boundary: Boundary):
        if boundary == "routine":
            return self.runner.step_to_next_routine(max_raw=self.max_raw)
        if boundary == "instruction":
            return self.runner.step_to_next_instruction(max_raw=self.max_raw)
        if boundary == "block":
            return self.runner.step_to_next_block(max_raw=self.max_raw)
        if boundary == "source":
            return self.runner.step_to_next_source_step(max_raw=self.max_raw)
        raise ValueError(f"unknown boundary: {boundary}")

    def _group_back(self, boundary: Boundary):
        if boundary == "routine":
            return self.runner.back_to_previous_routine()
        if boundary == "instruction":
            return self.runner.back_to_previous_instruction()
        if boundary == "block":
            return self.runner.back_to_previous_block()
        if boundary == "source":
            return self.runner.back_to_previous_source_step()
        raise ValueError(f"unknown boundary: {boundary}")

    def _display_source(self) -> RawTransitionSource | None:
        return self.runner.current_transition_source or self.runner.last_transition_source

    def _format_status_line(self) -> str:
        return (
            f"status: {self.runner.run_status} raw_step={self.runner.current.steps} "
            f"max_raw={self.max_raw} history={self.runner.history_cursor}/{self.runner.latest_history_index}"
        )

    def _format_snapshot_line(self, snapshot: RawTraceSnapshot, *, include_raw_step: bool) -> str:
        read_symbol = snapshot.tape.get(snapshot.head, self.runner.program.blank)
        prefix = f"snapshot: raw_step={snapshot.steps} " if include_raw_step else "snapshot: "
        return f"{prefix}state={snapshot.state!r} head={snapshot.head} read={read_symbol!r}"

    def _format_where_header(self, source: RawTransitionSource | None) -> str:
        if source is None:
            return "where: <unmapped>"
        routine = source.routine_name if source.routine_index is None else f"{source.routine_index}:{source.routine_name}"
        instruction = "setup" if source.instruction_index is None else str(source.instruction_index)
        return f"where: block={source.block_label} instruction={instruction} routine={routine} op={source.op_index}"

    def _format_source_row(self, source: RawTransitionSource) -> str:
        return f"row: state={source.state!r} read={source.read_symbol!r}"

    def _format_action_row(self) -> str | None:
        key = self.runner.current_transition_key
        row = self.runner.current_transition
        if key is None or row is None:
            return None
        next_state, write_symbol, move = row
        state, read_symbol = key
        return (
            f"row: state={state!r} read={read_symbol!r} -> "
            f"next={next_state!r} write={write_symbol!r} move={_format_move(move)}"
        )

    def _format_instruction_line(self, source: RawTransitionSource | None) -> str | None:
        if source is None or source.instruction_text is None:
            return None
        return f"instruction: {source.instruction_text}"

    def _format_semantic_lines(self, decoded_view, decode_error: str | None) -> list[str]:
        if decoded_view is not None:
            return _format_decoded_view(decoded_view, semantic_window=self.semantic_window)
        if decode_error is not None:
            return [f"semantic: <decode error: {decode_error}>"]
        return ["semantic: unavailable"]


__all__ = [
    "ActionStatus",
    "Boundary",
    "DebuggerActionResult",
    "DebuggerSession",
]
