"""Benchmark raw transition simplification passes on the incrementer UTM."""

from __future__ import annotations

import csv
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mtm.compiler import Compiler
from mtm.debugger import RawTraceRunner
from mtm.lowering import lower_program_with_source_map
from mtm.raw_transition_optimization import merge_identical_transition_states, prune_unreachable_transitions
from mtm.raw_transition_tm import TMTransitionProgram, run_raw_tm
from mtm.semantic_objects import RawTMInstance, compile_raw_guest
from mtm.source_file import load_python_tm_instance
from mtm.universal import UniversalInterpreter


FUEL = 1_000_000
L2_SOURCE_STEP_FUEL = 10_000_000


@dataclass(frozen=True)
class BenchmarkRow:
    name: str
    transitions: int
    transition_percent: float
    l1_input_band_width: int
    direct_raw_steps: int
    direct_status: str
    encoded_guest_band_width: int
    l2_first_source_raw_steps: int
    l2_first_source_status: str


def _initial_band_width(tape: dict[int, str]) -> int:
    if not tape:
        return 0
    return max(tape) - min(tape) + 1


def _compile_incrementer() -> tuple[TMTransitionProgram, dict[int, str], int]:
    source = ROOT / "examples" / "incrementer_tm.py"
    encoded = Compiler().compile(load_python_tm_instance(source))
    band_artifact = encoded.to_band_artifact()
    program_artifact = UniversalInterpreter.for_encoded(encoded).lower_for_band(band_artifact)
    return program_artifact.program, band_artifact.to_runtime_tape(), band_artifact.start_head


def _measure(
    name: str,
    program: TMTransitionProgram,
    baseline_transitions: int,
    tape: dict[int, str],
    head: int,
) -> BenchmarkRow:
    direct_result = run_raw_tm(program, tape, head=head, max_steps=FUEL)
    encoded_guest = compile_raw_guest(RawTMInstance(
        program=program,
        tape=tape,
        head=head,
        state=program.start_state,
    ))
    encoded_guest_band = encoded_guest.to_band_artifact()
    l2_first_source_status, l2_first_source_raw_steps = _l2_first_source_step(encoded_guest, encoded_guest_band)
    return BenchmarkRow(
        name=name,
        transitions=len(program.prog),
        transition_percent=(len(program.prog) / baseline_transitions) * 100,
        l1_input_band_width=_initial_band_width(tape),
        direct_raw_steps=int(direct_result["steps"]),
        direct_status=str(direct_result["status"]),
        encoded_guest_band_width=_initial_band_width(encoded_guest_band.to_runtime_tape()),
        l2_first_source_raw_steps=l2_first_source_raw_steps,
        l2_first_source_status=l2_first_source_status,
    )


def _l2_first_source_step(encoded_guest, encoded_guest_band) -> tuple[str, int]:
    interpreter = UniversalInterpreter.for_encoded(encoded_guest)
    lowered = lower_program_with_source_map(
        interpreter.to_meta_asm(),
        interpreter.alphabet_for_band(encoded_guest_band),
    )
    runner = RawTraceRunner(
        lowered.raw_program,
        encoded_guest_band.to_runtime_tape(),
        head=encoded_guest_band.start_head,
        state=lowered.raw_program.start_state,
        source_map=lowered.source_map,
    )
    result = runner.stream_to_next_source_step(max_raw=L2_SOURCE_STEP_FUEL)
    return result.status, result.raw_steps


def benchmark_rows() -> list[BenchmarkRow]:
    baseline, tape, head = _compile_incrementer()
    baseline_transitions = len(baseline.prog)
    variants: tuple[tuple[str, Callable[[TMTransitionProgram], TMTransitionProgram]], ...] = (
        ("none", lambda program: program),
        ("reachable", prune_unreachable_transitions),
        ("merged", merge_identical_transition_states),
        ("reachable+merged", lambda program: merge_identical_transition_states(prune_unreachable_transitions(program))),
        ("merged+reachable", lambda program: prune_unreachable_transitions(merge_identical_transition_states(program))),
    )
    return [
        _measure(name, optimize(baseline), baseline_transitions, tape, head)
        for name, optimize in variants
    ]


def main() -> int:
    writer = csv.writer(sys.stdout)
    writer.writerow([
        "optimization",
        "transitions",
        "transition_percent",
        "l1_input_band_width",
        "direct_raw_steps",
        "direct_status",
        "encoded_guest_band_width",
        "l2_first_source_raw_steps",
        "l2_first_source_status",
    ])
    for row in benchmark_rows():
        writer.writerow([
            row.name,
            row.transitions,
            f"{row.transition_percent:.2f}",
            row.l1_input_band_width,
            row.direct_raw_steps,
            row.direct_status,
            row.encoded_guest_band_width,
            row.l2_first_source_raw_steps,
            row.l2_first_source_status,
        ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
