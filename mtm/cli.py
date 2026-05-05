"""Artifact-oriented CLI for MTM pipelines."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .compiler import Compiler
from .debugger import DebuggerSession, DebuggerShell, RawTraceRunner
from .lowering import ACTIVE_RULE, lower_program_with_source_map
from .meta_asm import build_universal_meta_asm
from .utm_band_layout import EncodedBand, split_runtime_tape
from .meta_asm import format_program
from . import load_fixture
from .pretty import pretty_registers, pretty_tape
from .source_file import load_python_tm_instance, source_artifact_from_python
from .semantic_objects import RawTMInstance, UTMBandArtifact, UTMEncoded, UTMProgramArtifact, compile_raw_guest, start_head_from_encoded_band
from .source_encoding import TMAbi
from .universal import UniversalInterpreter


TRACE_DEFAULT_MAX_RAW = 100_000
TRACE_SOURCE_DEFAULT_MAX_RAW = 5_000_000


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


def _artifact_stem(path: str | Path) -> str:
    name = Path(path).name
    for suffix in (".mtm.source", ".utm.band", ".tm", ".py"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return Path(path).stem


def _l1_artifact_paths(out_dir: str | Path, stem: str) -> tuple[Path, Path, Path]:
    out = Path(out_dir)
    return out / f"{stem}.mtm.source", out / f"{stem}.l1.utm.band", out / f"{stem}.l1.tm"


def _l2_artifact_paths(out_dir: str | Path, stem: str) -> tuple[Path, Path]:
    out = Path(out_dir)
    return out / f"{stem}.l2.utm.band", out / f"{stem}.l2.tm"


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


def _source_fields(source) -> tuple[object, object, object, object, object, object]:
    if source is None:
        return ("", "", "", "", "", "")
    instruction_index = "setup" if source.instruction_index is None else source.instruction_index
    return (
        source.block_label,
        instruction_index,
        "" if source.routine_index is None else source.routine_index,
        source.routine_name,
        source.op_index,
        source.instruction_text or "",
    )


def _simulated_symbol_at(view, address: int) -> str:
    tape = view.simulated_tape
    if address < 0:
        index = address + len(tape.left_band)
        if 0 <= index < len(tape.left_band):
            return tape.left_band[index]
        return tape.blank
    if address < len(tape.right_band):
        return tape.right_band[address]
    return tape.blank


def _decoded_guest_view(session: DebuggerSession):
    view = session.runner.current_view(encoding=session.encoding)
    if view.decoded_view is None:
        detail = f": {view.decode_error}" if view.decode_error is not None else ""
        raise SystemExit(f"source trace could not decode simulated guest{detail}")
    return view.decoded_view


def _build_trace_session(
    tm_file: str | Path,
    band_file: str | Path,
    *,
    max_raw: int,
) -> DebuggerSession:
    band_artifact = UTMBandArtifact.read(band_file)
    program_artifact = UTMProgramArtifact.read(tm_file)
    interpreter = UniversalInterpreter.for_encoded(band_artifact)
    lowered = lower_program_with_source_map(
        interpreter.to_meta_asm(),
        interpreter.alphabet_for_band(band_artifact),
    )
    if lowered.raw_program.prog != program_artifact.program.prog:
        raise SystemExit("trace requires a .tm matching the UTM lowering for BAND_FILE")
    if lowered.raw_program.start_state != program_artifact.program.start_state:
        raise SystemExit("trace requires matching .tm start_state")
    if lowered.raw_program.halt_state != program_artifact.program.halt_state:
        raise SystemExit("trace requires matching .tm halt_state")

    return DebuggerSession(
        RawTraceRunner(
            program_artifact.program,
            band_artifact.to_runtime_tape(),
            head=band_artifact.start_head,
            state=program_artifact.program.start_state,
            source_map=lowered.source_map,
        ),
        encoding=band_artifact.encoding,
        max_raw=max_raw,
    )


def _write_trace_meta(args, session: DebuggerSession, *, max_raw: int) -> None:
    if args.meta_out is None:
        return
    snapshot = session.runner.current
    meta = {
        "format": "mtm-trace-meta-v1",
        "tm_file": str(args.tm_file),
        "band_file": str(args.band_file),
        "level": args.level,
        "max_steps": args.max_steps,
        "max_raw": max_raw,
        "blank": session.runner.program.blank,
        "initial_state": snapshot.state,
        "initial_head": snapshot.head,
        "initial_steps": snapshot.steps,
        "initial_tape": {
            str(address): symbol
            for address, symbol in sorted(snapshot.tape.items())
        },
    }
    output = Path(args.meta_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def _write_trace(args) -> int:
    if args.max_steps <= 0:
        raise SystemExit("--max-steps must be positive")
    max_raw = args.max_raw
    if max_raw is None:
        max_raw = TRACE_SOURCE_DEFAULT_MAX_RAW if args.level in {"source", "guest"} else TRACE_DEFAULT_MAX_RAW
    if max_raw <= 0:
        raise SystemExit("--max-raw must be positive")

    session = _build_trace_session(
        args.tm_file,
        args.band_file,
        max_raw=max_raw,
    )
    _write_trace_meta(args, session, max_raw=max_raw)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        if args.level == "raw":
            writer.writerow([
                "step",
                "status",
                "state",
                "read",
                "write",
                "move",
                "next_state",
                "head_after",
                "block",
                "instruction_index",
                "routine_index",
                "routine_name",
                "op_index",
                "instruction",
            ])
            for _ in range(args.max_steps):
                result = session.runner.stream_step()
                transition = result.transition
                if transition is None:
                    writer.writerow([
                        result.snapshot.steps,
                        result.status,
                        result.snapshot.state,
                        "",
                        "",
                        "",
                        "",
                        result.snapshot.head,
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ])
                    break
                writer.writerow([
                    transition.step,
                    result.status,
                    transition.state,
                    transition.read_symbol,
                    transition.write_symbol,
                    transition.move,
                    transition.next_state,
                    result.snapshot.head,
                    *_source_fields(transition.source),
                ])
            return 0

        if args.level in ("source", "guest"):
            writer.writerow([
                "group",
                "status",
                "raw_start",
                "raw_end",
                "raw_delta",
                "state",
                "read",
                "write",
                "move",
                "next_state",
                "head_before",
                "head_after",
                "block",
                "instruction_index",
                "routine_index",
                "routine_name",
                "op_index",
                "instruction",
            ])
            for group in range(args.max_steps):
                start = session.runner.current
                before = _decoded_guest_view(session)
                head_before = before.simulated_head
                read_symbol = _simulated_symbol_at(before, head_before)
                source = session.runner.current_transition_source
                result = session.runner.stream_to_next_source_step(max_raw=max_raw)
                after = _decoded_guest_view(session)
                head_after = after.simulated_head
                write_symbol = _simulated_symbol_at(after, head_before)
                writer.writerow([
                    group,
                    result.status,
                    start.steps + 1 if result.raw_steps else start.steps,
                    result.snapshot.steps,
                    result.raw_steps,
                    before.current_state,
                    read_symbol,
                    write_symbol,
                    head_after - head_before,
                    after.current_state,
                    head_before,
                    head_after,
                    *_source_fields(source),
                ])
                if result.status != "stepped":
                    break
            return 0

        writer.writerow([
            "group",
            "status",
            "raw_start",
            "raw_end",
            "raw_delta",
            "start_state",
            "start_head",
            "end_state",
            "end_head",
            "block",
            "instruction_index",
            "routine_index",
            "routine_name",
            "op_index",
            "instruction",
        ])
        for group in range(args.max_steps):
            start = session.runner.current
            source = session.runner.current_transition_source
            if args.level == "instruction":
                result = session.runner.stream_to_next_instruction(max_raw=max_raw)
            else:
                result = session.runner.stream_to_next_block(max_raw=max_raw)
            writer.writerow([
                group,
                result.status,
                start.steps + 1 if result.raw_steps else start.steps,
                result.snapshot.steps,
                result.raw_steps,
                start.state,
                start.head,
                result.snapshot.state,
                result.snapshot.head,
                *_source_fields(source),
            ])
            if result.status != "stepped":
                break
    return 0


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

    source_parser = sub.add_parser("emit-source", help="Emit a safe .mtm.source artifact from a Python TM file.")
    source_parser.add_argument("input")
    source_parser.add_argument("-o", "--output", required=True)

    l1_parser = sub.add_parser("l1", help="Emit source, l1 .utm.band, and l1 .tm artifacts from a Python TM file.")
    l1_parser.add_argument("input")
    l1_parser.add_argument("--out-dir", required=True)
    l1_parser.add_argument("--stem")
    _add_abi_args(l1_parser)

    l2_parser = sub.add_parser("l2", help="Emit l2 artifacts from l1 .tm and l1 .utm.band artifacts.")
    l2_parser.add_argument("tm_file")
    l2_parser.add_argument("band_file")
    l2_parser.add_argument("--out-dir", required=True)
    l2_parser.add_argument("--stem")

    run_parser = sub.add_parser("run", help="Run a .tm program on a .utm.band artifact.")
    run_parser.add_argument("tm_file")
    run_parser.add_argument("input", nargs="?")
    run_parser.add_argument("--max-steps", type=int, default=200_000)

    trace_parser = sub.add_parser("trace", help="Emit a TSV trace for a .tm program and .utm.band input.")
    trace_parser.add_argument("tm_file")
    trace_parser.add_argument("band_file")
    trace_parser.add_argument("--out", required=True)
    trace_parser.add_argument("--level", choices=("raw", "instruction", "block", "source", "guest"), default="raw")
    trace_parser.add_argument("--max-steps", type=int, default=100)
    trace_parser.add_argument("--max-raw", type=int)
    trace_parser.add_argument("--meta-out")

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

    if args.command == "emit-source":
        source_artifact_from_python(args.input).write(args.output)
        return 0

    if args.command == "l1":
        stem = args.stem or _artifact_stem(args.input)
        source_path, band_path, tm_path = _l1_artifact_paths(args.out_dir, stem)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_artifact_from_python(args.input).write(source_path)
        _encoded, band_artifact, _interpreter, program_artifact = _compile_from_py(args.input, abi=abi)
        band_artifact.write(band_path)
        program_artifact.write(tm_path)
        return 0

    if args.command == "l2":
        stem = args.stem or _artifact_stem(args.band_file).removesuffix(".l1")
        band_path, tm_path = _l2_artifact_paths(args.out_dir, stem)
        band_path.parent.mkdir(parents=True, exist_ok=True)
        l1_program_artifact = UTMProgramArtifact.read(args.tm_file)
        l1_band_artifact = UTMBandArtifact.read(args.band_file)
        raw_guest = RawTMInstance(
            program=l1_program_artifact.program,
            tape=l1_band_artifact.to_runtime_tape(),
            head=l1_band_artifact.start_head,
            state=l1_program_artifact.program.start_state,
        )
        encoded = compile_raw_guest(raw_guest)
        band_artifact = encoded.to_band_artifact()
        program_artifact = UniversalInterpreter.for_encoded(encoded).lower_for_band(band_artifact)
        band_artifact.write(band_path)
        program_artifact.write(tm_path)
        return 0

    if args.command == "dbg":
        return _run_fixture_debugger(_resolve_debugger_fixture_name(args))

    if args.command == "trace":
        return _write_trace(args)

    if args.input is None:
        raise SystemExit("run requires INPUT.utm.band")
    artifact = UTMBandArtifact.read(args.input)
    band = artifact.to_encoded_band()
    program_artifact = UTMProgramArtifact.read(args.tm_file)
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
