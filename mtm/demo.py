"""Tiny demo entrypoint for exploring MTM fixtures."""

from __future__ import annotations

import argparse

from .fixtures import list_fixtures, load_fixture
from .meta_asm import build_universal_meta_asm, format_program
from .meta_interpreter import format_meta_trace, run_meta_asm_host
from .outer_tape import EncodedBand, split_outer_tape
from .pretty import pretty_fixture, pretty_registers, pretty_tape

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show an MTM fixture and its encoded band.")
    parser.add_argument("fixture", nargs="?", default="incrementer")
    parser.add_argument("--list", action="store_true", help="List available fixtures.")
    parser.add_argument("--asm", action="store_true", help="Show the compiled Meta-ASM program too.")
    parser.add_argument("--run-asm", action="store_true", help="Run the Meta-ASM host interpreter and show its trace.")
    parser.add_argument("--max-steps", type=int, default=500, help="Maximum host-interpreter steps for --run-asm.")
    parser.add_argument("--show-outer", action="store_true", help="Show concrete outer tape addresses too.")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(list_fixtures()))
        return 0

    fixture = load_fixture(args.fixture)
    band = fixture.build_band()
    program = build_universal_meta_asm(band.encoding)

    print(pretty_fixture(fixture, show_outer=args.show_outer))
    if args.asm or args.run_asm:
        print()
        print("=" * 88)
        print()
        print("META-ASM")
        print()
        print(format_program(program))
    if args.run_asm:
        status, final_outer_tape, trace, reason = run_meta_asm_host(program, band.encoding, band.outer_tape, max_steps=args.max_steps)
        final_left_band, final_right_band = split_outer_tape(final_outer_tape)
        final_band = EncodedBand(band.encoding, final_outer_tape, final_left_band, final_right_band)
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
    return 0


__all__ = ["main"]
