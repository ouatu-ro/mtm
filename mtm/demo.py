"""Tiny demo entrypoint for exploring MTM fixtures."""

from __future__ import annotations

import argparse
from typing import Any

from .fixtures import list_fixtures, load_fixture
from .compiler import Compiler
from .compiled_band import EncodedBand, split_runtime_tape
from .lowering_checks import lowering_smoke_rows
from .meta_asm import format_program
from .meta_asm_host import format_meta_trace, run_meta_asm_runtime
from .pretty import pretty_fixture, pretty_registers, pretty_tape, table
from .program_input import load_python_tm
from .raw_tm import format_raw_tm, run_raw_tm
from .semantic_objects import TMBand, TMInstance
from .universal import UniversalInterpreter


def _instance_from_fixture(fixture: Any) -> TMInstance:
    cells = tuple([fixture.blank] * fixture.blanks_left + fixture.input_symbols + [fixture.blank] * fixture.blanks_right)
    return TMInstance(
        program=fixture.tm_program,
        band=TMBand(cells=cells, head=fixture.blanks_left, blank=fixture.blank),
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show an MTM fixture and its encoded runtime band.")
    parser.add_argument("fixture", nargs="?", default="incrementer")
    parser.add_argument("--list", action="store_true", help="List available fixtures.")
    parser.add_argument("--tm-file", help="Load a plain Python TM definition file instead of a fixture.")
    parser.add_argument("--asm", action="store_true", help="Show the compiled Meta-ASM program too.")
    parser.add_argument("--run-asm", action="store_true", help="Run the Meta-ASM host interpreter and show its trace.")
    parser.add_argument("--emit-raw-tm", action="store_true", help="Show the lowered raw TM for the universal interpreter.")
    parser.add_argument("--run-utm", action="store_true", help="Run the lowered raw TM on the generated runtime tape.")
    parser.add_argument("--test-lowering", action="store_true", help="Run smoke checks for the first lowered raw-TM fragments.")
    parser.add_argument("--max-steps", type=int, default=500, help="Maximum host-interpreter steps for --run-asm.")
    parser.add_argument("--max-raw-steps", type=int, default=200_000, help="Maximum raw-TM steps for --run-utm.")
    parser.add_argument("--show-runtime", action="store_true", help="Show the concrete runtime tape addresses too.")
    parser.add_argument("--show-outer", action="store_true", help="Compatibility alias for --show-runtime.")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(list_fixtures()))
        return 0

    fixture = load_python_tm(args.tm_file) if args.tm_file else load_fixture(args.fixture)
    instance = _instance_from_fixture(fixture)
    encoded = Compiler().compile(instance)
    band_artifact = encoded.to_band_artifact()
    band = band_artifact.to_encoded_band()
    interpreter = UniversalInterpreter.for_encoded(encoded)
    program = interpreter.to_meta_asm()
    program_artifact = interpreter.lower_for_band(band_artifact)
    raw_tm = program_artifact.program

    print(pretty_fixture(fixture, show_runtime=args.show_runtime or args.show_outer))
    if args.asm or args.run_asm:
        print()
        print("=" * 88)
        print()
        print("META-ASM")
        print()
        print(format_program(program))
    if args.run_asm:
        status, final_runtime_tape, trace, reason = run_meta_asm_runtime(program, band.encoding, band.runtime_tape, max_steps=args.max_steps)
        final_left_band, final_right_band = split_runtime_tape(final_runtime_tape)
        final_band = EncodedBand(band.encoding, final_left_band, final_right_band)
        print()
        print("=" * 88)
        print()
        print("META-ASM TRACE")
        print()
        print(format_meta_trace(trace))
        print()
        print(f"FINAL STATUS: {status}")
        print(f"REASON: {reason}")
        print()
        print("FINAL REGISTERS")
        print()
        print(pretty_registers(final_band.encoding, final_band.left_band))
        print()
        print("=" * 88)
        print()
        print("FINAL TAPE")
        print()
        print(pretty_tape(final_band.encoding, final_band.right_band))
    if args.emit_raw_tm:
        print()
        print("=" * 88)
        print()
        print("RAW UTM")
        print()
        print(format_raw_tm(raw_tm))
    if args.run_utm:
        config = band_artifact.to_run_config(program_artifact)
        result = run_raw_tm(raw_tm, config.tape, head=config.head, state=config.state, max_steps=args.max_raw_steps)
        final_left_band, final_right_band = split_runtime_tape(result["tape"])
        final_band = EncodedBand(band.encoding, final_left_band, final_right_band)
        print()
        print("=" * 88)
        print()
        print("RAW UTM RESULT")
        print()
        print(f"FINAL STATUS: {result['status']}")
        print(f"FINAL STATE: {result['state']}")
        print(f"FINAL HEAD: {result['head']}")
        print(f"STEPS: {result['steps']}")
        print()
        print("FINAL REGISTERS")
        print()
        print(pretty_registers(final_band.encoding, final_band.left_band))
        print()
        print("=" * 88)
        print()
        print("FINAL TAPE")
        print()
        print(pretty_tape(final_band.encoding, final_band.right_band))
    if args.test_lowering:
        print()
        print("=" * 88)
        print()
        print("LOWERING SMOKE TESTS")
        print()
        print(table(["instruction", "status", "state", "head", "note"], lowering_smoke_rows(fixture)))
    return 0


__all__ = ["main"]
