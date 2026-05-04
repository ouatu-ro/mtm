"""Artifact-oriented CLI for MTM pipelines."""

from __future__ import annotations

import argparse
from pathlib import Path

from .artifacts import read_tm, read_utm_artifact, write_tm, write_utm_artifact
from .lowering import ACTIVE_RULE, lower_program_to_raw_tm
from .meta_asm import build_universal_meta_asm, format_program
from .compiled_band import CUR_STATE, EncodedBand, split_runtime_tape
from .pretty import pretty_registers, pretty_tape
from .program_input import load_python_tm
from .raw_tm import run_raw_tm
from .semantic_objects import utm_artifact_from_band
from .tape_encoding import TMAbi


def _target_abi_from_args(args) -> TMAbi | None:
    widths = [getattr(args, "state_width", None), getattr(args, "symbol_width", None), getattr(args, "dir_width", None)]
    if all(width is None for width in widths):
        return None
    if any(width is None for width in widths):
        raise SystemExit("explicit ABI requires --state-width, --symbol-width, and --dir-width together")
    return TMAbi(
        state_width=args.state_width,
        symbol_width=args.symbol_width,
        dir_width=args.dir_width,
        family_label=f"U[Wq={args.state_width},Ws={args.symbol_width},Wd={args.dir_width}]",
    )


def _compile_from_py(path: str | Path, *, abi: TMAbi | None = None):
    fixture = load_python_tm(path)
    band = fixture.build_band(abi=abi)
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    raw_tm = lower_program_to_raw_tm(program, alphabet)
    return fixture, band, program, raw_tm


def _add_abi_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-width", type=int)
    parser.add_argument("--symbol-width", type=int)
    parser.add_argument("--dir-width", type=int)


def _write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(text + ("\n" if not text.endswith("\n") else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile and run MTM artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser("compile", help="Compile a Python TM file into a runtime-band .utm artifact.")
    compile_parser.add_argument("input")
    compile_parser.add_argument("-o", "--output", required=True)
    compile_parser.add_argument("--asm-out")
    compile_parser.add_argument("--tm-out")
    _add_abi_args(compile_parser)

    asm_parser = sub.add_parser("emit-asm", help="Emit width-specialized Meta-ASM for a Python TM file.")
    asm_parser.add_argument("input")
    asm_parser.add_argument("-o", "--output", required=True)
    _add_abi_args(asm_parser)

    tm_parser = sub.add_parser("emit-tm", help="Emit lowered raw UTM .tm for a Python TM file.")
    tm_parser.add_argument("input")
    tm_parser.add_argument("-o", "--output", required=True)
    _add_abi_args(tm_parser)

    run_parser = sub.add_parser("run", help="Run a raw .tm program on a .utm artifact or a plain string tape.")
    run_parser.add_argument("tm_file")
    run_parser.add_argument("input", nargs="?")
    run_parser.add_argument("--input-string")
    run_parser.add_argument("--head", type=int, default=0)
    run_parser.add_argument("--blank", default="_")
    run_parser.add_argument("--max-steps", type=int, default=200_000)

    args = parser.parse_args(argv)
    abi = _target_abi_from_args(args)

    if args.command == "compile":
        _fixture, band, program, raw_tm = _compile_from_py(args.input, abi=abi)
        write_utm_artifact(args.output, utm_artifact_from_band(band))
        if args.asm_out:
            _write_text(args.asm_out, format_program(program))
        if args.tm_out:
            write_tm(args.tm_out, raw_tm)
        return 0

    if args.command == "emit-asm":
        _fixture, _band, program, _raw_tm = _compile_from_py(args.input, abi=abi)
        _write_text(args.output, format_program(program))
        return 0

    if args.command == "emit-tm":
        _fixture, _band, _program, raw_tm = _compile_from_py(args.input, abi=abi)
        write_tm(args.output, raw_tm)
        return 0

    tm = read_tm(args.tm_file)
    if args.input_string is not None:
        tape = dict(enumerate(args.input_string))
        result = run_raw_tm(tm, tape, head=args.head, max_steps=args.max_steps)
        print(f"FINAL STATUS: {result['status']}")
        print(f"FINAL STATE: {result['state']}")
        print(f"FINAL HEAD: {result['head']}")
        print(f"STEPS: {result['steps']}")
        cells = "".join(result["tape"].get(i, args.blank) for i in range(min(result["tape"], default=0), max(result["tape"], default=-1) + 1))
        print(cells)
        return 0

    if args.input is None:
        raise SystemExit("run requires either INPUT.utm or --input-string")
    artifact = read_utm_artifact(args.input)
    band = artifact.to_encoded_band()
    start_head = artifact.start_head
    runtime_tape = band.runtime_tape
    result = run_raw_tm(tm, runtime_tape, head=start_head, max_steps=args.max_steps)
    final_left_band, final_right_band = band.left_band, band.right_band
    if result["tape"] != runtime_tape:
        final_left_band, final_right_band = split_runtime_tape(result["tape"])
    final_band = EncodedBand(band.encoding, final_left_band, final_right_band)
    print(f"FINAL STATUS: {result['status']}")
    print(f"FINAL STATE: {result['state']}")
    print(f"FINAL HEAD: {result['head']}")
    print(f"STEPS: {result['steps']}")
    print()
    print("FINAL REGISTERS")
    print()
    print(pretty_registers(final_band.encoding, final_band.left_band))
    print()
    print("FINAL TAPE")
    print()
    print(pretty_tape(final_band.encoding, final_band.right_band))
    return 0


__all__ = ["main"]
