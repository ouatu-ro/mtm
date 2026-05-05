"""Benchmark raw transition simplification passes on the incrementer UTM."""

from __future__ import annotations

import csv
import sys
from argparse import ArgumentParser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mtm.compiler import Compiler
from mtm.debugger import RawTraceRunner
from mtm.lowering import lower_program_with_source_map
from mtm.raw_transition_optimization import (
    merge_identical_transition_states,
    prune_unreachable_transitions,
    right_biased_raw_guest_state_order,
)
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
    encoded_guest_band_width: int | None
    l2_source_steps: int | None
    l2_source_raw_steps: int | None
    l2_source_status: str | None


@dataclass(frozen=True)
class BenchmarkVariant:
    name: str
    optimize: Callable[[TMTransitionProgram], TMTransitionProgram]
    state_order: Callable[[RawTMInstance], tuple[str, ...]] | None = None
    scatter_state_ids: bool = False


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
    *,
    expensive: bool,
    l2_source_steps: int,
    state_order: Callable[[RawTMInstance], tuple[str, ...]] | None = None,
    scatter_state_ids: bool = False,
) -> BenchmarkRow:
    direct_result = run_raw_tm(program, tape, head=head, max_steps=FUEL)
    encoded_guest_band_width = None
    l2_source_status = None
    l2_source_raw_steps = None
    if expensive:
        raw_instance = RawTMInstance(
            program=program,
            tape=tape,
            head=head,
            state=program.start_state,
        )
        encoded_guest = compile_raw_guest(
            raw_instance,
            state_order=() if state_order is None else state_order(raw_instance),
            scatter_state_ids=scatter_state_ids,
        )
        encoded_guest_band = encoded_guest.to_band_artifact()
        encoded_guest_band_width = _initial_band_width(encoded_guest_band.to_runtime_tape())
        l2_source_status, l2_source_raw_steps = _l2_source_steps(encoded_guest, encoded_guest_band, groups=l2_source_steps)
    return BenchmarkRow(
        name=name,
        transitions=len(program.prog),
        transition_percent=(len(program.prog) / baseline_transitions) * 100,
        l1_input_band_width=_initial_band_width(tape),
        direct_raw_steps=int(direct_result["steps"]),
        direct_status=str(direct_result["status"]),
        encoded_guest_band_width=encoded_guest_band_width,
        l2_source_steps=l2_source_steps if expensive else None,
        l2_source_raw_steps=l2_source_raw_steps,
        l2_source_status=l2_source_status,
    )


def _l2_source_steps(encoded_guest, encoded_guest_band, *, groups: int) -> tuple[str, int]:
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
    raw_steps = 0
    status = "stepped"
    for _group in range(groups):
        result = runner.stream_to_next_source_step(max_raw=L2_SOURCE_STEP_FUEL)
        raw_steps += result.raw_steps
        status = result.status
        if status != "stepped":
            break
    return status, raw_steps


def benchmark_rows(*, expensive: bool = False, l2_source_steps: int = 1) -> list[BenchmarkRow]:
    baseline, tape, head = _compile_incrementer()
    baseline_transitions = len(baseline.prog)
    variants = (
        BenchmarkVariant("none", lambda program: program),
        BenchmarkVariant("reachable", prune_unreachable_transitions),
        BenchmarkVariant("merged", merge_identical_transition_states),
        BenchmarkVariant("reachable+merged", lambda program: merge_identical_transition_states(prune_unreachable_transitions(program))),
        BenchmarkVariant("merged+reachable", lambda program: prune_unreachable_transitions(merge_identical_transition_states(program))),
        BenchmarkVariant("right-biased-renumber", lambda program: program, right_biased_raw_guest_state_order, True),
        BenchmarkVariant("merged+right-biased-renumber", merge_identical_transition_states, right_biased_raw_guest_state_order, True),
        BenchmarkVariant(
            "merged+reachable+right-biased-renumber",
            lambda program: prune_unreachable_transitions(merge_identical_transition_states(program)),
            right_biased_raw_guest_state_order,
            True,
        ),
    )
    return [
        _measure(
            variant.name,
            variant.optimize(baseline),
            baseline_transitions,
            tape,
            head,
            expensive=expensive,
            l2_source_steps=l2_source_steps,
            state_order=variant.state_order,
            scatter_state_ids=variant.scatter_state_ids,
        )
        for variant in variants
    ]


def _optional(value: object | None) -> object:
    return "" if value is None else value


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Benchmark raw transition simplification passes on the incrementer UTM.")
    parser.add_argument(
        "--expensive",
        action="store_true",
        help="include encoded raw-guest band width and first L2 source-step measurements",
    )
    parser.add_argument(
        "--l2-source-steps",
        type=int,
        default=1,
        help="number of interpreted source steps to run for --expensive L2 measurements",
    )
    args = parser.parse_args(argv)
    if args.l2_source_steps <= 0:
        raise SystemExit("--l2-source-steps must be positive")

    writer = csv.writer(sys.stdout)
    writer.writerow([
        "optimization",
        "transitions",
        "transition_percent",
        "l1_input_band_width",
        "direct_raw_steps",
        "direct_status",
        "encoded_guest_band_width",
        "l2_source_steps",
        "l2_source_raw_steps",
        "l2_source_status",
    ])
    for row in benchmark_rows(expensive=args.expensive, l2_source_steps=args.l2_source_steps):
        writer.writerow([
            row.name,
            row.transitions,
            f"{row.transition_percent:.2f}",
            row.l1_input_band_width,
            row.direct_raw_steps,
            row.direct_status,
            _optional(row.encoded_guest_band_width),
            _optional(row.l2_source_steps),
            _optional(row.l2_source_raw_steps),
            _optional(row.l2_source_status),
        ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
