"""Standalone text helpers for low-level raw-trace inspection.

These helpers turn raw trace state into compact plain text that can be read in
tests, terminals, and teaching notes without needing the richer document
renderers.
"""

from __future__ import annotations

from ..lowering.source_map import RawTransitionSource
from ..semantic_objects import DecodedBandView, UTMSimulatedTape
from .trace import RawTraceGroupStepResult, RawTraceView


def format_source_location(source: RawTransitionSource | None, *, label: str = "source") -> str:
    if source is None:
        return f"{label}: <unmapped>"

    routine = source.routine_name if source.routine_index is None else f"{source.routine_index}:{source.routine_name}"
    instruction = "?" if source.instruction_index is None else str(source.instruction_index)
    lines = [
        f"{label}: block={source.block_label} instruction={instruction} routine={routine} op={source.op_index}",
        f"row: state={source.state!r} read={source.read_symbol!r}",
    ]
    if source.instruction_text is not None:
        lines.append(f"instruction: {source.instruction_text}")
    return "\n".join(lines)


def format_trace_view(
    view: RawTraceView,
    *,
    raw_window: int = 2,
    semantic_window: int = 2,
    blank_symbol: str = ".",
) -> str:
    lines = [
        f"snapshot: step={view.snapshot.steps} state={view.snapshot.state!r} head={view.snapshot.head}",
        f"raw tape: {_format_sparse_tape(view.snapshot.tape, head=view.snapshot.head, radius=raw_window, blank_symbol=blank_symbol)}",
    ]
    if view.next_raw_transition_key is None or view.next_raw_transition_row is None:
        lines.append("next raw: <none>")
    else:
        lines.append(f"next raw: {_format_transition(view.next_raw_transition_key, view.next_raw_transition_row)}")

    source = view.next_raw_transition_source
    if source is not None:
        lines.append(format_source_location(source))
    elif view.last_transition_source is not None:
        lines.append(format_source_location(view.last_transition_source, label="last source"))
    else:
        lines.append("source: <unmapped>")

    if view.last_transition is None:
        lines.append("last raw: <none>")
    else:
        lines.append(f"last raw: {_format_last_transition(view.last_transition)}")

    if view.decoded_view is not None:
        lines.extend(_format_decoded_view(view.decoded_view, semantic_window=semantic_window))
    elif view.decode_error is not None:
        lines.append(f"semantic: <decode error: {view.decode_error}>")
    else:
        lines.append("semantic: <not requested>")

    return "\n".join(lines)


def format_group_step_result(
    result: RawTraceGroupStepResult,
    *,
    source: RawTransitionSource | None = None,
) -> str:
    lines = [
        f"group step: status={result.status} raw_steps={result.raw_steps}",
        f"snapshot: step={result.snapshot.steps} state={result.snapshot.state!r} head={result.snapshot.head}",
    ]
    if source is not None:
        lines.append(format_source_location(source))
    return "\n".join(lines)


def _format_transition(key, row) -> str:
    next_state, write_symbol, move = row
    state, read_symbol = key
    return f"({state!r}, {read_symbol!r}) -> ({next_state!r}, {write_symbol!r}, {_format_move(move)})"


def _format_last_transition(transition) -> str:
    return _format_transition(
        transition.key,
        (transition.next_state, transition.write_symbol, transition.move),
    )


def _format_decoded_view(view: DecodedBandView, *, semantic_window: int) -> list[str]:
    registers = view.registers
    tmp_bits = "".join(registers.tmp_bits) or "-"
    return [
        f"semantic: state={view.current_state!r} head={view.simulated_head}",
        f"semantic tape: {_format_semantic_tape(view.simulated_tape, radius=semantic_window)}",
        "registers: "
        f"cur={registers.cur_state!r} read={registers.cur_symbol!r} write={registers.write_symbol!r} "
        f"next={registers.next_state!r} move={_format_move(registers.move_dir)} cmp={registers.cmp_flag!r} tmp={tmp_bits!r}",
    ]


def _format_semantic_tape(tape: UTMSimulatedTape, *, radius: int) -> str:
    cells: dict[int, str] = {
        **{index - len(tape.left_band): symbol for index, symbol in enumerate(tape.left_band)},
        **{index: symbol for index, symbol in enumerate(tape.right_band)},
    }
    return _format_sparse_tape(cells, head=tape.head, radius=radius, blank_symbol=tape.blank)


def _format_sparse_tape(tape, *, head: int, radius: int, blank_symbol: str) -> str:
    cells = []
    for address in range(head - radius, head + radius + 1):
        symbol = tape.get(address, blank_symbol)
        cell = f"{address}:{symbol!r}"
        cells.append(f"[{cell}]" if address == head else cell)
    return " ".join(cells)


def _format_move(move: int) -> str:
    if move < 0:
        return "L"
    if move > 0:
        return "R"
    return "S"


__all__ = [
    "format_group_step_result",
    "format_source_location",
    "format_trace_view",
]
