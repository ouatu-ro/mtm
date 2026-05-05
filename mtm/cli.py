"""Artifact-oriented CLI for MTM pipelines."""

from __future__ import annotations

import argparse
from pathlib import Path

from .compiler import Compiler
from .debugger import DebuggerSession, DebuggerShell, RawTraceRunner
from .lowering import ACTIVE_RULE, lower_program_with_source_map
from .meta_asm import build_universal_meta_asm
from .utm_band_layout import EncodedBand, split_runtime_tape
from .meta_asm import format_program
from . import load_fixture
from .pretty import pretty_registers, pretty_tape
from .source_file import load_python_tm_instance
from .raw_transition_tm import TMTransitionProgram
from .semantic_objects import UTMBandArtifact, UTMEncoded, UTMProgramArtifact, start_head_from_encoded_band
from .source_encoding import TMAbi
from .universal import UniversalInterpreter


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


def _compile_from_py(path: str | Path, *, abi: TMAbi | None = None) -> tuple[UTMEncoded, UTMBandArtifact, UniversalInterpreter, UTMProgramArtifact]:
    instance = load_python_tm_instance(path)
    encoded = Compiler(target_abi=abi).compile(instance)
    band_artifact = encoded.to_band_artifact()
    interpreter = UniversalInterpreter.for_encoded(encoded)
    program_artifact = interpreter.lower_for_band(band_artifact)
    return encoded, band_artifact, interpreter, program_artifact


def _add_abi_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-width", type=int)
    parser.add_argument("--symbol-width", type=int)
    parser.add_argument("--dir-width", type=int)


def _write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(text + ("\n" if not text.endswith("\n") else ""))


def _build_fixture_debugger_session(name: str) -> DebuggerSession:
    fixture = load_fixture(name)
    band = fixture.build_band()
    program = build_universal_meta_asm(band.encoding)
    band_symbols = band.linear() if hasattr(band, "linear") else tuple(band.runtime_tape.values())
    alphabet = sorted(set(band_symbols) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        band.runtime_tape,
        head=start_head_from_encoded_band(band),
        state=program.entry_label,
        source_map=lowered.source_map,
    )
    return DebuggerSession(runner, encoding=band.encoding)


def _run_fixture_debugger(name: str) -> int:
    session = _build_fixture_debugger_session(name)
    shell = DebuggerShell(session)
    startup = shell.render_startup(name)
    formatter = getattr(shell, "format_output", None)
    print(formatter(startup) if callable(formatter) else startup)
    shell.cmdloop()
    return 0


def _resolve_debugger_fixture_name(args) -> str:
    if args.fixture_name is not None:
        if args.fixture is not None and args.fixture != args.fixture_name:
            raise SystemExit("dbg accepts one fixture name via FIXTURE or --fixture, not both")
        return args.fixture_name
    if args.fixture is None:
        raise SystemExit("dbg requires FIXTURE or --fixture FIXTURE")
    return args.fixture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile and run MTM artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser("compile", help="Compile a Python TM file into a .utm.band artifact.")
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

    run_parser = sub.add_parser("run", help="Run a .tm program on a .utm.band artifact.")
    run_parser.add_argument("tm_file")
    run_parser.add_argument("input", nargs="?")
    run_parser.add_argument("--max-steps", type=int, default=200_000)

    dbg_parser = sub.add_parser("dbg", help="Start the MTM debugger REPL for a fixture.")
    dbg_parser.add_argument("fixture", nargs="?")
    dbg_parser.add_argument("--fixture", dest="fixture_name")

    args = parser.parse_args(argv)
    abi = _target_abi_from_args(args)

    if args.command == "compile":
        _encoded, band_artifact, interpreter, program_artifact = _compile_from_py(args.input, abi=abi)
        band_artifact.write(args.output)
        if args.asm_out:
            _write_text(args.asm_out, format_program(interpreter.to_meta_asm()))
        if args.tm_out:
            program_artifact.write(args.tm_out)
        return 0

    if args.command == "emit-asm":
        _encoded, _band_artifact, interpreter, _program_artifact = _compile_from_py(args.input, abi=abi)
        _write_text(args.output, format_program(interpreter.to_meta_asm()))
        return 0

    if args.command == "emit-tm":
        _encoded, _band_artifact, _interpreter, program_artifact = _compile_from_py(args.input, abi=abi)
        program_artifact.write(args.output)
        return 0

    if args.command == "dbg":
        return _run_fixture_debugger(_resolve_debugger_fixture_name(args))

    tm = TMTransitionProgram.read(args.tm_file)
    if args.input is None:
        raise SystemExit("run requires INPUT.utm.band")
    artifact = UTMBandArtifact.read(args.input)
    band = artifact.to_encoded_band()
    program_artifact = UTMProgramArtifact(program=tm, target_abi=artifact.target_abi, minimal_abi=artifact.minimal_abi)
    config = artifact.to_raw_instance(program_artifact)
    runtime_tape = dict(config.tape)
    result = program_artifact.run(artifact, fuel=args.max_steps)
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
