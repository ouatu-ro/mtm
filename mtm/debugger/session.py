"""Session-layer debugger semantics over a raw trace runner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..lowering.source_map import RawTransitionSource
from ..source_encoding import Encoding
from .render import (
    DebuggerActionSummary,
    DebuggerLocationSummary,
    DebuggerRenderer,
    DebuggerRunnerSummary,
    DebuggerSemanticSummary,
    DebuggerTransitionSummary,
    DebuggerViewSummary,
    _format_move,
    _format_sparse_tape,
    explain_meta_instruction,
)
from .trace import RawTraceRunner, RawTraceSnapshot

Boundary = Literal["raw", "routine", "instruction", "block", "source"]
ActionStatus = Literal["stepped", "rewound", "halted", "stuck", "max_raw", "unmapped", "at_start"]


@dataclass(frozen=True)
class DebuggerActionResult:
    """User-facing result for one debugger action."""

    boundary: Boundary
    status: ActionStatus
    raw_delta: int
    snapshot: RawTraceSnapshot
    count_completed: int = 1
    count_requested: int = 1


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
        renderer: DebuggerRenderer | None = None,
    ) -> None:
        if max_raw <= 0:
            raise ValueError("max_raw must be positive")
        self.runner = runner
        self.encoding = encoding
        self.max_raw = max_raw
        self.raw_window = raw_window
        self.semantic_window = semantic_window
        self.renderer = DebuggerRenderer(color=False) if renderer is None else renderer

    def status_summary(self) -> tuple[DebuggerRunnerSummary, DebuggerLocationSummary]:
        return self._runner_summary(self.runner.current), self._location_summary(self._display_source())

    def where_summary(self) -> tuple[DebuggerLocationSummary, DebuggerTransitionSummary]:
        return self._location_summary(self._display_source()), self._next_transition_summary()

    def view_summary(self) -> DebuggerViewSummary:
        view = self.runner.current_view(encoding=self.encoding)
        source = view.next_raw_transition_source or view.last_transition_source
        return DebuggerViewSummary(
            runner=self._runner_summary(view.snapshot),
            location=self._location_summary(source),
            next_row=self._transition_from_key_row(view.next_raw_transition_key, view.next_raw_transition_row),
            last_row=self._last_transition_summary(),
            raw_tape=_format_sparse_tape(
                view.snapshot.tape,
                head=view.snapshot.head,
                radius=self.raw_window,
                blank_symbol=self.runner.program.blank,
            ),
            semantic=self._semantic_summary(view),
        )

    def status_text(self) -> str:
        runner, location = self.status_summary()
        return self.renderer.render_status(runner=runner, location=location)

    def where_text(self) -> str:
        location, next_row = self.where_summary()
        return self.renderer.render_where(location=location, next_row=next_row)

    def view_text(self) -> str:
        return self.renderer.render_view(self.view_summary())

    def step(self, boundary: Boundary) -> DebuggerActionResult:
        if boundary == "raw":
            step_result = self.runner.step()
            return DebuggerActionResult(
                boundary=boundary,
                status=step_result.status,
                raw_delta=1 if step_result.status == "stepped" else 0,
                snapshot=step_result.snapshot,
            )

        result = self._group_step(boundary)
        return DebuggerActionResult(
            boundary=boundary,
            status=result.status,
            raw_delta=result.raw_steps,
            snapshot=result.snapshot,
        )

    def step_text(self, boundary: Boundary) -> str:
        return self.step_many_text(boundary, 1)

    def step_many(self, boundary: Boundary, count: int) -> DebuggerActionResult:
        if count <= 0:
            raise ValueError("count must be positive")
        total_raw_delta = 0
        completed = 0
        last_result: DebuggerActionResult | None = None
        for _ in range(count):
            result = self.step(boundary)
            last_result = result
            total_raw_delta += result.raw_delta
            if result.status == "stepped":
                completed += 1
                continue
            break
        assert last_result is not None
        return DebuggerActionResult(
            boundary=boundary,
            status=last_result.status,
            raw_delta=total_raw_delta,
            snapshot=last_result.snapshot,
            count_completed=completed,
            count_requested=count,
        )

    def step_many_text(self, boundary: Boundary, count: int) -> str:
        return self.renderer.render_action(self.action_summary("step", self.step_many(boundary, count)))

    def back(self, boundary: Boundary) -> DebuggerActionResult:
        if boundary == "raw":
            rewound = self.runner.back()
            return DebuggerActionResult(
                boundary=boundary,
                status="rewound" if rewound else "at_start",
                raw_delta=-1 if rewound else 0,
                snapshot=self.runner.current,
            )

        result = self._group_back(boundary)
        return DebuggerActionResult(
            boundary=boundary,
            status="rewound" if result.status == "stepped" else result.status,
            raw_delta=-result.raw_steps if result.status == "stepped" else 0,
            snapshot=result.snapshot,
        )

    def back_text(self, boundary: Boundary) -> str:
        return self.back_many_text(boundary, 1)

    def back_many(self, boundary: Boundary, count: int) -> DebuggerActionResult:
        if count <= 0:
            raise ValueError("count must be positive")
        total_raw_delta = 0
        completed = 0
        last_result: DebuggerActionResult | None = None
        for _ in range(count):
            result = self.back(boundary)
            last_result = result
            total_raw_delta += result.raw_delta
            if result.status == "rewound":
                completed += 1
                continue
            break
        assert last_result is not None
        return DebuggerActionResult(
            boundary=boundary,
            status=last_result.status,
            raw_delta=total_raw_delta,
            snapshot=last_result.snapshot,
            count_completed=completed,
            count_requested=count,
        )

    def back_many_text(self, boundary: Boundary, count: int) -> str:
        return self.renderer.render_action(self.action_summary("back", self.back_many(boundary, count)))

    def action_summary(self, verb: Literal["step", "back"], result: DebuggerActionResult) -> DebuggerActionSummary:
        return DebuggerActionSummary(
            verb=verb,
            boundary=result.boundary,
            status=result.status,
            raw_delta=result.raw_delta,
            runner=self._runner_summary(result.snapshot),
            location=self._location_summary(self._display_source()),
            next_row=self._next_transition_summary(),
            count_completed=result.count_completed,
            count_requested=result.count_requested,
        )

    def set_max_raw(self, value: int) -> str:
        if value <= 0:
            raise ValueError("max_raw must be positive")
        self.max_raw = value
        return self.renderer.render_set_max_raw(self.max_raw)

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

    def _runner_summary(self, snapshot: RawTraceSnapshot) -> DebuggerRunnerSummary:
        return DebuggerRunnerSummary(
            run_status=self.runner.run_status,
            raw=snapshot.steps,
            max_raw=self.max_raw,
            hist_current=self.runner.history_cursor,
            hist_last=self.runner.latest_history_index,
            state=snapshot.state,
            head=snapshot.head,
            read_symbol=snapshot.tape.get(snapshot.head, self.runner.program.blank),
        )

    def _location_summary(self, source: RawTransitionSource | None) -> DebuggerLocationSummary:
        if source is None:
            return DebuggerLocationSummary(
                mapped=False,
                block=None,
                instr=None,
                routine=None,
                op=None,
                instruction_text=None,
                instruction_help=None,
            )
        routine = source.routine_name if source.routine_index is None else f"{source.routine_index}:{source.routine_name}"
        return DebuggerLocationSummary(
            mapped=True,
            block=source.block_label,
            instr="setup" if source.instruction_index is None else str(source.instruction_index),
            routine=routine,
            op=source.op_index,
            instruction_text=source.instruction_text,
            instruction_help=explain_meta_instruction(source.instruction),
        )

    def _next_transition_summary(self) -> DebuggerTransitionSummary:
        return self._transition_from_key_row(self.runner.current_transition_key, self.runner.current_transition)

    def _transition_from_key_row(self, key, row) -> DebuggerTransitionSummary:
        if key is None or row is None:
            return DebuggerTransitionSummary(
                present=False,
                state=None,
                read_symbol=None,
                write_symbol=None,
                move=None,
                next_state=None,
            )
        state, read_symbol = key
        next_state, write_symbol, move = row
        return DebuggerTransitionSummary(
            present=True,
            state=state,
            read_symbol=read_symbol,
            write_symbol=write_symbol,
            move=_format_move(move),
            next_state=next_state,
        )

    def _last_transition_summary(self) -> DebuggerTransitionSummary:
        transition = self.runner.last_transition
        if transition is None:
            return DebuggerTransitionSummary(
                present=False,
                state=None,
                read_symbol=None,
                write_symbol=None,
                move=None,
                next_state=None,
            )
        return DebuggerTransitionSummary(
            present=True,
            state=transition.state,
            read_symbol=transition.read_symbol,
            write_symbol=transition.write_symbol,
            move=_format_move(transition.move),
            next_state=transition.next_state,
        )

    def _semantic_summary(self, view) -> DebuggerSemanticSummary:
        if view.decoded_view is None:
            if view.decode_error is not None:
                return DebuggerSemanticSummary(status="error", decode_error=view.decode_error)
            return DebuggerSemanticSummary(status="unavailable")

        decoded_view = view.decoded_view
        head = decoded_view.simulated_tape.head
        tape_cells = {
            **{index - len(decoded_view.simulated_tape.left_band): symbol for index, symbol in enumerate(decoded_view.simulated_tape.left_band)},
            **{index: symbol for index, symbol in enumerate(decoded_view.simulated_tape.right_band)},
        }
        registers = decoded_view.registers
        return DebuggerSemanticSummary(
            status="available",
            state=decoded_view.current_state,
            head=head,
            symbol=tape_cells.get(head, decoded_view.simulated_tape.blank),
            tape=_format_sparse_tape(
                tape_cells,
                head=head,
                radius=self.semantic_window,
                blank_symbol=decoded_view.simulated_tape.blank,
            ),
            cur=registers.cur_state,
            read=registers.cur_symbol,
            write=registers.write_symbol,
            next=registers.next_state,
            move=_format_move(registers.move_dir),
            cmp=registers.cmp_flag,
            tmp="".join(registers.tmp_bits) or "-",
        )


__all__ = [
    "ActionStatus",
    "Boundary",
    "DebuggerActionResult",
    "DebuggerSession",
]
