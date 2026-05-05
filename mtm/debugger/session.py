"""Session-layer debugger semantics over raw trace, facts, and queries.

``DebuggerSession`` sits above ``RawTraceRunner`` and turns raw stepping into
user commands, query rows, and boundary-aware repeat/back operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..source_encoding import Encoding
from .facts import TraceFacts
from .queries import ActionRow, DebuggerQueries, StatusRow, ViewRow, WhereRow
from .trace import RawTraceRunner, RawTraceSnapshot

Boundary = Literal["raw", "routine", "instruction", "block", "source"]
ActionStatus = Literal["stepped", "rewound", "halted", "stuck", "max_raw", "unmapped", "at_start"]


@dataclass(frozen=True)
class DebuggerActionResult:
    """The raw outcome of one debugger command before query projection.

    The shell turns this object into the more polished query rows shown to the
    user, so it keeps the low-level execution details close to the command that
    produced them.
    """

    boundary: Boundary
    status: ActionStatus
    raw_delta: int
    snapshot: RawTraceSnapshot
    count_completed: int = 1
    count_requested: int = 1


class DebuggerSession:
    """User-facing debugger commands layered over a raw trace runner.

    This layer is where raw stepping becomes debugger behavior: it refreshes
    derived facts, applies boundary-aware repeat commands, and exposes the
    status, where, and view rows consumed by the presenter.
    """

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
        """Build a debugger session around an existing raw trace runner."""

        if max_raw <= 0:
            raise ValueError("max_raw must be positive")
        self.runner = runner
        self.encoding = encoding
        self.max_raw = max_raw
        self.facts = TraceFacts(
            runner,
            encoding=encoding,
            raw_window=raw_window,
            semantic_window=semantic_window,
        )
        self.queries = DebuggerQueries(self.facts, max_raw=max_raw)

    def status(self) -> StatusRow:
        """Return the current status row after refreshing derived facts."""

        self._refresh_queries()
        return self.queries.status()

    def where(self) -> WhereRow:
        """Return the current source-location row after refreshing facts."""

        self._refresh_queries()
        return self.queries.where()

    def view(self) -> ViewRow:
        """Return the current combined raw and semantic view row."""

        self._refresh_queries()
        return self.queries.view()

    def step(self, boundary: Boundary) -> DebuggerActionResult:
        """Step forward by one raw row or one grouped boundary."""

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

    def step_many(self, boundary: Boundary, count: int) -> ActionRow:
        """Repeat a step command and collapse the result into one action row."""

        result = self._repeat(boundary, count, direction="step")
        self._refresh_queries()
        return self.queries.action(
            verb="step",
            boundary=result.boundary,
            status=result.status,
            raw_delta=result.raw_delta,
            count_completed=result.count_completed,
            count_requested=result.count_requested,
        )

    def back(self, boundary: Boundary) -> DebuggerActionResult:
        """Step backward by one raw row or one grouped boundary."""

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

    def back_many(self, boundary: Boundary, count: int) -> ActionRow:
        """Repeat a back command and collapse the result into one action row."""

        result = self._repeat(boundary, count, direction="back")
        self._refresh_queries()
        return self.queries.action(
            verb="back",
            boundary=result.boundary,
            status=result.status,
            raw_delta=result.raw_delta,
            count_completed=result.count_completed,
            count_requested=result.count_requested,
        )

    def set_max_raw(self, value: int) -> int:
        """Update the maximum raw steps allowed for grouped stepping."""

        if value <= 0:
            raise ValueError("max_raw must be positive")
        self.max_raw = value
        self.queries.max_raw = value
        return value

    def _repeat(self, boundary: Boundary, count: int, *, direction: Literal["step", "back"]) -> DebuggerActionResult:
        if count <= 0:
            raise ValueError("count must be positive")
        total_raw_delta = 0
        completed = 0
        last_result: DebuggerActionResult | None = None
        for _ in range(count):
            result = self.step(boundary) if direction == "step" else self.back(boundary)
            last_result = result
            total_raw_delta += result.raw_delta
            if result.status in {"stepped", "rewound"}:
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

    def _refresh_queries(self) -> None:
        self.facts.rebuild_from_trace()
        self.queries.max_raw = self.max_raw


__all__ = [
    "ActionStatus",
    "Boundary",
    "DebuggerActionResult",
    "DebuggerSession",
]
