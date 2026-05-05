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
from mtm.raw_transition_optimization import merge_identical_transition_states, prune_unreachable_transitions
from mtm.raw_transition_tm import TMTransitionProgram, run_raw_tm
from mtm.source_file import load_python_tm_instance
from mtm.universal import UniversalInterpreter


FUEL = 1_000_000


@dataclass(frozen=True)
class BenchmarkRow:
    name: str
    transitions: int
    transition_percent: float
    initial_band_width: int
    steps: int
    status: str


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
    result = run_raw_tm(program, tape, head=head, max_steps=FUEL)
    return BenchmarkRow(
        name=name,
        transitions=len(program.prog),
        transition_percent=(len(program.prog) / baseline_transitions) * 100,
        initial_band_width=_initial_band_width(tape),
        steps=int(result["steps"]),
        status=str(result["status"]),
    )


def benchmark_rows() -> list[BenchmarkRow]:
    baseline, tape, head = _compile_incrementer()
    baseline_transitions = len(baseline.prog)
    variants: tuple[tuple[str, Callable[[TMTransitionProgram], TMTransitionProgram]], ...] = (
        ("none", lambda program: program),
        ("reachable", prune_unreachable_transitions),
        ("merged", merge_identical_transition_states),
        ("reachable+merged", lambda program: merge_identical_transition_states(prune_unreachable_transitions(program))),
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
        "initial_band_width",
        "steps",
        "status",
    ])
    for row in benchmark_rows():
        writer.writerow([
            row.name,
            row.transitions,
            f"{row.transition_percent:.2f}",
            row.initial_band_width,
            row.steps,
            row.status,
        ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
