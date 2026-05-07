"""Artifact-oriented CLI for MTM pipelines."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tomllib
from pathlib import Path

from .artifacts import RAW_TM_FORMAT, SOURCE_FORMAT, UTM_BAND_FORMAT, _read_literal_assignments
from .compiler import Compiler
from .debugger import DebuggerSession, DebuggerShell, RawTraceRunner
from .lowering import ACTIVE_RULE, lower_program_with_source_map
from .meta_asm import build_universal_meta_asm
from .utm_band_layout import EncodedTape, split_runtime_tape
from .meta_asm import format_program
from . import load_fixture
from .pretty import pretty_registers, pretty_tape, table
from .source_file import load_python_tm_instance, source_artifact_from_python
from .semantic_objects import RawTMInstance, SourceArtifact, UTMBandArtifact, UTMEncoded, UTMProgramArtifact, compile_raw_guest, decoded_view_from_encoded_tape, start_head_from_encoded_tape
from .source_encoding import TMAbi
from .universal import UniversalInterpreter


TRACE_DEFAULT_MAX_RAW = 100_000
TRACE_SOURCE_DEFAULT_MAX_RAW = 5_000_000
DEBUG_DEFAULT_MAX_RAW = DebuggerSession.DEFAULT_MAX_RAW


class MTMHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Argparse formatter that keeps multiline examples readable."""


TOP_LEVEL_HELP = """\
Compile, inspect, and run Meta Turing Machine artifacts.

Common workflows:
  mtm compile examples/source/incrementer_tm.py -o out/incrementer.utm.band --tm-out out/incrementer.tm
  mtm run out/incrementer.tm out/incrementer.utm.band
  mtm inspect out/incrementer.utm.band
  mtm concepts UTMBandArtifact
  mtm trace out/incrementer.tm out/incrementer.utm.band --level raw --out out/raw.tsv --meta-out out/raw.json
  mtm dbg incrementer
  mtm dbg out/incrementer.tm out/incrementer.utm.band

Run `mtm COMMAND -h` for command-specific inputs, outputs, and examples.
"""


COMMAND_EXAMPLES = {
    "compile": """\
Compile a Python source TM into an encoded guest tape artifact.

ABI width flags:
  --state-width, --symbol-width, and --dir-width must be supplied together.

Examples:
  mtm compile examples/source/incrementer_tm.py -o out/incrementer.utm.band
  mtm compile examples/source/incrementer_tm.py -o out/incrementer.utm.band --tm-out out/incrementer.tm --asm-out out/incrementer.asm
  mtm compile examples/source/incrementer_tm.py -o out/wide.utm.band --state-width 3 --symbol-width 4 --dir-width 2
""",
    "emit-asm": """\
Emit the width-specialized Meta-ASM interpreter for a Python source TM.

ABI width flags:
  --state-width, --symbol-width, and --dir-width must be supplied together.

Examples:
  mtm emit-asm examples/source/incrementer_tm.py -o out/incrementer.asm
  mtm emit-asm examples/source/incrementer_tm.py -o out/wide.asm --state-width 3 --symbol-width 4 --dir-width 2
""",
    "emit-tm": """\
Emit the lowered raw UTM transition table for a Python source TM.

ABI width flags:
  --state-width, --symbol-width, and --dir-width must be supplied together.

Examples:
  mtm emit-tm examples/source/incrementer_tm.py -o out/incrementer.tm
  mtm emit-tm examples/source/incrementer_tm.py -o out/wide.tm --state-width 3 --symbol-width 4 --dir-width 2
""",
    "emit-source": """\
Emit a safe source artifact from a Python source TM.

Example:
  mtm emit-source examples/source/incrementer_tm.py -o out/incrementer.mtm.source
""",
    "l1": """\
Emit the standard L1 bundle from a Python source TM.

Outputs:
  STEM.mtm.source
  STEM.l1.utm.band
  STEM.l1.tm

ABI width flags:
  --state-width, --symbol-width, and --dir-width must be supplied together.

Examples:
  mtm l1 examples/source/incrementer_tm.py --out-dir out
  mtm l1 examples/source/incrementer_tm.py --out-dir out --stem incrementer --state-width 3 --symbol-width 4 --dir-width 2
""",
    "l2": """\
Emit L2 artifacts by compiling an L1 raw TM plus its L1 band as a raw guest.

Outputs:
  STEM.l2.utm.band
  STEM.l2.tm

Example:
  mtm l2 out/incrementer.l1.tm out/incrementer.l1.utm.band --out-dir out
""",
    "run": """\
Run a raw UTM .tm program on a .utm.band input artifact.

Views:
  decoded  decoded simulated guest tape and registers (default)
  encoded  concrete split encoded UTM tape
  raw      sparse raw TM runtime tape

Examples:
  mtm run out/incrementer.l1.tm out/incrementer.l1.utm.band --max-steps 200000
  mtm run out/incrementer.tm out/incrementer.utm.band --view decoded
  mtm run out/incrementer.tm out/incrementer.utm.band --view encoded --when final
  mtm run out/incrementer.tm out/incrementer.utm.band --view raw --around-head 80
  mtm run out/incrementer.tm out/incrementer.utm.band --view raw --range -200:120
  mtm run out/incrementer.tm out/incrementer.utm.band --view encoded --side right
""",
    "inspect": """\
Summarize MTM artifacts without running them.

Recognized artifact formats:
  .utm.band    encoded UTM input artifact
  .tm          raw transition program artifact
  .mtm.source  safe source-machine artifact

Examples:
  mtm inspect out/incrementer.utm.band
  mtm inspect out/incrementer.tm out/incrementer.mtm.source
""",
    "concepts": """\
Show the local MTM vocabulary used by docs and CLI output.

Examples:
  mtm concepts
  mtm concepts UTMBandArtifact
  mtm concepts SourceTape EncodedTape runtime_tape
""",
    "trace": """\
Emit a TSV trace for a raw UTM run.

Levels:
  raw          one row per raw transition
  instruction  one row per Meta-ASM instruction boundary
  block        one row per Meta-ASM block boundary
  source|guest one row per simulated guest/source step

Raw guard defaults:
  raw/instruction/block: 100000
  source/guest:          5000000

Examples:
  mtm trace out/incrementer.l1.tm out/incrementer.l1.utm.band --level raw --max-steps 500 --out out/raw.tsv --meta-out out/raw.json
  mtm trace out/incrementer.l1.tm out/incrementer.l1.utm.band --level instruction --max-steps 50 --out out/instruction.tsv
""",
    "dbg": """\
Start the interactive debugger REPL.

Inputs:
  mtm dbg FIXTURE
  mtm dbg HOST.tm INPUT.utm.band

Examples:
  mtm dbg incrementer
  mtm dbg out/incrementer.l1.tm out/incrementer.l1.utm.band --max-raw 100000
""",
}


CONCEPTS_PATH = Path(__file__).resolve().parents[1] / "docs" / "reference" / "concepts.toml"


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
    parser.add_argument("--state-width", type=int, metavar="WQ", help="target ABI state field width")
    parser.add_argument("--symbol-width", type=int, metavar="WS", help="target ABI symbol field width")
    parser.add_argument("--dir-width", type=int, metavar="WD", help="target ABI direction field width")


def _add_command(
    subparsers,
    name: str,
    *,
    help: str,
    description: str | None = None,
) -> argparse.ArgumentParser:
    return subparsers.add_parser(
        name,
        help=help,
        description=description or help,
        epilog=COMMAND_EXAMPLES[name],
        formatter_class=MTMHelpFormatter,
    )


def _write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(text + ("\n" if not text.endswith("\n") else ""))


def _load_concepts() -> dict[str, object]:
    try:
        with CONCEPTS_PATH.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"concepts file not found: {CONCEPTS_PATH}") from exc
    return dict(data)


def _concept_names_for_help() -> str:
    try:
        names = sorted(_load_concepts())
    except SystemExit:
        return "  unavailable; concepts file could not be loaded"
    return "  " + "\n  ".join(names)


def _format_concept(name: str, concept: dict[str, object]) -> str:
    lines = [
        name,
        f"  kind: {concept.get('kind', '-')}",
        f"  summary: {concept.get('summary', '-')}",
    ]
    meaning = concept.get("meaning")
    if meaning:
        lines.append(f"  meaning: {meaning}")
    not_items = concept.get("not")
    if isinstance(not_items, dict) and not_items:
        lines.append("  not the same thing as:")
        lines.extend(f"    {other}: {description}" for other, description in not_items.items())
    docs = concept.get("docs")
    if isinstance(docs, list) and docs:
        lines.append("  docs:")
        lines.extend(f"    {doc}" for doc in docs)
    return "\n".join(lines)


def _show_concepts(args) -> int:
    concepts = _load_concepts()
    if not args.names:
        rows = [
            [name, data.get("kind", "-"), data.get("summary", "-")]
            for name, data in sorted(concepts.items())
            if isinstance(data, dict)
        ]
        print("MTM CONCEPTS")
        print()
        print(table(["name", "kind", "summary"], rows))
        print()
        print("Use `mtm concepts NAME` for details.")
        return 0

    missing = [name for name in args.names if name not in concepts]
    if missing:
        known = ", ".join(sorted(concepts))
        raise SystemExit(f"unknown concept(s): {', '.join(missing)}\nknown concepts: {known}")
    print("\n\n".join(_format_concept(name, concepts[name]) for name in args.names))
    return 0


def _format_abi(abi: TMAbi | None) -> str:
    if abi is None:
        return "-"
    label = abi.family_label or f"U[Wq={abi.state_width},Ws={abi.symbol_width},Wd={abi.dir_width}]"
    return f"{label} grammar={abi.grammar_version}"


def _format_encoding_summary(encoding) -> str:
    return (
        f"states={len(encoding.state_ids)} width={encoding.state_width}; "
        f"symbols={len(encoding.symbol_ids)} width={encoding.symbol_width}; "
        f"dirs={len(encoding.direction_ids)} width={encoding.direction_width}"
    )


def _inspect_utm_band(path: Path) -> str:
    artifact = UTMBandArtifact.read(path)
    encoded_tape = artifact.to_encoded_tape()
    lines = [
        f"{path}: MTM UTM band artifact",
        f"  format: {UTM_BAND_FORMAT}",
        f"  concept: UTMBandArtifact (more: mtm concepts UTMBandArtifact)",
        f"  target ABI: {_format_abi(artifact.target_abi)}",
        f"  minimal ABI: {_format_abi(artifact.minimal_abi)}",
        f"  encoding: {_format_encoding_summary(artifact.encoding)}",
        f"  left band tokens: {len(artifact.left_band)}",
        f"  right band tokens: {len(artifact.right_band)}",
        f"  start head: {artifact.start_head}",
    ]
    try:
        view = decoded_view_from_encoded_tape(encoded_tape)
    except ValueError as exc:
        lines.append(f"  decoded view: unavailable ({exc})")
    else:
        simulated_tape = view.simulated_tape
        lines.extend([
            f"  decoded state: {view.current_state}",
            f"  decoded simulated head: {view.simulated_head}",
            f"  decoded source tape width: left={len(simulated_tape.left_band)} right={len(simulated_tape.right_band)}",
            f"  rules: {len(view.rules)}",
        ])
    return "\n".join(lines)


def _inspect_tm_program(path: Path) -> str:
    artifact = UTMProgramArtifact.read(path)
    program = artifact.program
    states = {program.start_state, program.halt_state}
    symbols = {program.blank, *program.alphabet}
    for (state, read_symbol), (next_state, write_symbol, _move) in program.prog.items():
        states.update((state, next_state))
        symbols.update((read_symbol, write_symbol))
    return "\n".join([
        f"{path}: MTM raw TM program artifact",
        f"  format: {RAW_TM_FORMAT}",
        f"  concept: UTMProgramArtifact (more: mtm concepts UTMProgramArtifact)",
        f"  target ABI: {_format_abi(artifact.target_abi)}",
        f"  minimal ABI: {_format_abi(artifact.minimal_abi)}",
        f"  transitions: {len(program.prog)}",
        f"  states: {len(states)}",
        f"  alphabet symbols: {len(symbols)}",
        f"  start state: {program.start_state}",
        f"  halt state: {program.halt_state}",
        f"  blank: {program.blank}",
    ])


def _inspect_source_artifact(path: Path) -> str:
    artifact = SourceArtifact.read(path)
    program = artifact.program
    tape = artifact.tape
    states = program.states(initial_state=artifact.initial_state, halt_state=artifact.halt_state)
    symbols = program.symbols(source_symbols=tape.cells, blank=tape.blank)
    lines = [
        f"{path}: MTM source artifact",
        f"  format: {SOURCE_FORMAT}",
        f"  concept: SourceArtifact (more: mtm concepts SourceArtifact)",
        f"  name: {artifact.name or '-'}",
        f"  transitions: {len(program.transitions)}",
        f"  states: {len(states)}",
        f"  source symbols: {len(symbols)}",
        f"  tape width: left={len(tape.left_band)} right={len(tape.right_band)}",
        f"  source head: {tape.head}",
        f"  initial state: {artifact.initial_state}",
        f"  halt state: {artifact.halt_state}",
        f"  blank: {tape.blank}",
    ]
    if artifact.note:
        lines.append(f"  note: {artifact.note}")
    return "\n".join(lines)


def _inspect_path(path: str | Path) -> str:
    artifact_path = Path(path)
    namespace = _read_literal_assignments(artifact_path)
    format_name = namespace.get("format")
    if format_name == UTM_BAND_FORMAT:
        return _inspect_utm_band(artifact_path)
    if format_name == RAW_TM_FORMAT:
        return _inspect_tm_program(artifact_path)
    if format_name == SOURCE_FORMAT:
        return _inspect_source_artifact(artifact_path)
    raise SystemExit(f"{artifact_path}: unknown MTM artifact format {format_name!r}")


def _inspect(args) -> int:
    print("\n\n".join(_inspect_path(path) for path in args.inputs))
    return 0


def _parse_range(value: str) -> tuple[int, int]:
    try:
        start_text, end_text = value.split(":", 1)
        start, end = int(start_text), int(end_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected START:END, for example -200:120") from exc
    if start > end:
        raise argparse.ArgumentTypeError("range start must be <= range end")
    return start, end


def _normalize_range_args(argv: list[str]) -> list[str]:
    normalized: list[str] = []
    index = 0
    while index < len(argv):
        if argv[index] == "--range" and index + 1 < len(argv):
            normalized.append(f"--range={argv[index + 1]}")
            index += 2
            continue
        normalized.append(argv[index])
        index += 1
    return normalized


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


def _build_fixture_debugger_session(name: str, *, max_raw: int = DEBUG_DEFAULT_MAX_RAW) -> DebuggerSession:
    fixture = load_fixture(name)
    encoded_tape = fixture.build_encoded_tape()
    program = build_universal_meta_asm(encoded_tape.encoding)
    tape_symbols = encoded_tape.linear() if hasattr(encoded_tape, "linear") else tuple(encoded_tape.runtime_tape.values())
    alphabet = sorted(set(tape_symbols) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        encoded_tape.runtime_tape,
        head=start_head_from_encoded_tape(encoded_tape),
        state=program.entry_label,
        source_map=lowered.source_map,
    )
    return DebuggerSession(runner, encoding=encoded_tape.encoding, max_raw=max_raw)


def _run_debugger(session: DebuggerSession, label: str) -> int:
    shell = DebuggerShell(session)
    startup = shell.render_startup(label)
    formatter = getattr(shell, "format_output", None)
    print(formatter(startup) if callable(formatter) else startup)
    shell.cmdloop()
    return 0


def _run_fixture_debugger(name: str, *, max_raw: int = DEBUG_DEFAULT_MAX_RAW) -> int:
    return _run_debugger(_build_fixture_debugger_session(name, max_raw=max_raw), name)


def _debugger_artifact_label(tm_file: str | Path, band_file: str | Path) -> str:
    return f"{Path(tm_file).name} on {Path(band_file).name}"


def _run_artifact_debugger(tm_file: str | Path, band_file: str | Path, *, max_raw: int) -> int:
    session = _build_trace_session(tm_file, band_file, max_raw=max_raw)
    return _run_debugger(session, _debugger_artifact_label(tm_file, band_file))


def _run_debugger_from_args(args) -> int:
    inputs = tuple(args.inputs)
    if args.fixture_name is not None:
        if inputs:
            raise SystemExit("dbg accepts either --fixture FIXTURE or positional inputs, not both")
        return _run_fixture_debugger(args.fixture_name, max_raw=args.max_raw)
    if len(inputs) == 1:
        return _run_fixture_debugger(inputs[0], max_raw=args.max_raw)
    if len(inputs) == 2:
        return _run_artifact_debugger(inputs[0], inputs[1], max_raw=args.max_raw)
    raise SystemExit("dbg requires FIXTURE or TM_FILE BAND_FILE")


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


def _result_header(result: dict[str, object], *, when: str) -> str:
    label = when.upper()
    return "\n".join([
        f"{label} STATUS: {result['status']}",
        f"{label} STATE: {result['state']}",
        f"{label} HEAD: {result['head']}",
        f"STEPS: {result['steps']}",
    ])


def _format_decoded_run_view(encoded_tape: EncodedTape, *, result: dict[str, object], when: str) -> str:
    decoded_view_from_encoded_tape(encoded_tape)
    label = when.upper()
    return "\n\n".join([
        _result_header(result, when=when),
        f"{label} REGISTERS\n\n{pretty_registers(encoded_tape.encoding, encoded_tape.left_band)}",
        f"{label} TAPE\n\n{pretty_tape(encoded_tape.encoding, encoded_tape.right_band)}",
    ])


def _encoded_rows(encoded_tape: EncodedTape, *, side: str) -> list[list[object]]:
    rows: list[list[object]] = []
    if side in {"both", "left"}:
        left_width = len(encoded_tape.left_band)
        rows.extend(["left", index, index - left_width, token] for index, token in enumerate(encoded_tape.left_band))
    if side in {"both", "right"}:
        rows.extend(["right", index, index, token] for index, token in enumerate(encoded_tape.right_band))
    return rows


def _format_encoded_run_view(encoded_tape: EncodedTape, *, result: dict[str, object], when: str, side: str) -> str:
    label = when.upper()
    return "\n\n".join([
        _result_header(result, when=when),
        f"{label} ENCODED TAPE ({side})",
        table(["side", "index", "runtime_addr", "token"], _encoded_rows(encoded_tape, side=side)),
    ])


def _raw_view_bounds(
    runtime_tape: dict[int, str],
    *,
    head: int,
    blank: str,
    raw_range: tuple[int, int] | None,
    around_head: int | None,
) -> tuple[int, int]:
    if raw_range is not None:
        return raw_range
    if around_head is not None:
        if around_head < 0:
            raise SystemExit("--around-head must be non-negative")
        return head - around_head, head + around_head
    live = [address for address, value in runtime_tape.items() if value != blank]
    if not live:
        return head, head
    return min([*live, head]), max([*live, head])


def _format_raw_run_view(
    runtime_tape: dict[int, str],
    *,
    result: dict[str, object],
    when: str,
    blank: str,
    raw_range: tuple[int, int] | None,
    around_head: int | None,
) -> str:
    head = int(result["head"])
    start, end = _raw_view_bounds(runtime_tape, head=head, blank=blank, raw_range=raw_range, around_head=around_head)
    rows = [
        [address, "yes" if address == head else "no", "left" if address < 0 else "right", runtime_tape.get(address, blank)]
        for address in range(start, end + 1)
    ]
    label = when.upper()
    return "\n\n".join([
        _result_header(result, when=when),
        f"{label} RAW RUNTIME TAPE ({start}:{end})",
        table(["addr", "head", "side", "value"], rows),
    ])


def _select_run_view(
    args,
    *,
    initial_encoded_tape: EncodedTape,
    final_encoded_tape: EncodedTape,
    initial_result: dict[str, object],
    final_result: dict[str, object],
    initial_runtime_tape: dict[int, str],
    final_runtime_tape: dict[int, str],
    blank: str,
) -> str:
    when = args.when
    encoded_tape = initial_encoded_tape if when == "initial" else final_encoded_tape
    result = initial_result if when == "initial" else final_result
    runtime_tape = initial_runtime_tape if when == "initial" else final_runtime_tape

    if args.view == "decoded":
        return _format_decoded_run_view(encoded_tape, result=result, when=when)
    if args.view == "encoded":
        return _format_encoded_run_view(encoded_tape, result=result, when=when, side=args.side)
    return _format_raw_run_view(
        runtime_tape,
        result=result,
        when=when,
        blank=blank,
        raw_range=args.raw_range,
        around_head=args.around_head,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile, inspect, and run MTM artifacts.",
        epilog=TOP_LEVEL_HELP,
        formatter_class=MTMHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, title="commands", metavar="COMMAND")

    compile_parser = _add_command(sub, "compile", help="Compile a Python TM file into a .utm.band artifact.")
    compile_parser.add_argument("input", metavar="INPUT.py", help="Python source TM file")
    compile_parser.add_argument("-o", "--output", required=True, metavar="OUTPUT.utm.band", help="encoded guest tape artifact to write")
    compile_parser.add_argument("--asm-out", metavar="OUTPUT.asm", help="also write the specialized Meta-ASM program")
    compile_parser.add_argument("--tm-out", metavar="OUTPUT.tm", help="also write the lowered raw UTM transition table")
    _add_abi_args(compile_parser)

    asm_parser = _add_command(sub, "emit-asm", help="Emit width-specialized Meta-ASM for a Python TM file.")
    asm_parser.add_argument("input", metavar="INPUT.py", help="Python source TM file")
    asm_parser.add_argument("-o", "--output", required=True, metavar="OUTPUT.asm", help="Meta-ASM file to write")
    _add_abi_args(asm_parser)

    tm_parser = _add_command(sub, "emit-tm", help="Emit lowered raw UTM .tm for a Python TM file.")
    tm_parser.add_argument("input", metavar="INPUT.py", help="Python source TM file")
    tm_parser.add_argument("-o", "--output", required=True, metavar="OUTPUT.tm", help="raw transition table to write")
    _add_abi_args(tm_parser)

    source_parser = _add_command(sub, "emit-source", help="Emit a safe .mtm.source artifact from a Python TM file.")
    source_parser.add_argument("input", metavar="INPUT.py", help="Python source TM file")
    source_parser.add_argument("-o", "--output", required=True, metavar="OUTPUT.mtm.source", help="source artifact to write")

    inspect_parser = _add_command(sub, "inspect", help="Summarize MTM artifact files.")
    inspect_parser.add_argument("inputs", nargs="+", metavar="ASSET", help=".utm.band, .tm, or .mtm.source artifact")

    concepts_parser = _add_command(sub, "concepts", help="Show MTM vocabulary and object distinctions.")
    concepts_parser.add_argument("names", nargs="*", metavar="NAME", help="concept name to describe")
    concepts_parser.epilog = COMMAND_EXAMPLES["concepts"] + "\nAvailable concepts:\n" + _concept_names_for_help()

    l1_parser = _add_command(sub, "l1", help="Emit source, l1 .utm.band, and l1 .tm artifacts from a Python TM file.")
    l1_parser.add_argument("input", metavar="INPUT.py", help="Python source TM file")
    l1_parser.add_argument("--out-dir", required=True, metavar="DIR", help="directory for the emitted L1 artifacts")
    l1_parser.add_argument("--stem", metavar="NAME", help="artifact filename stem; defaults to the input stem")
    _add_abi_args(l1_parser)

    l2_parser = _add_command(sub, "l2", help="Emit l2 artifacts from l1 .tm and l1 .utm.band artifacts.")
    l2_parser.add_argument("tm_file", metavar="L1.tm", help="L1 raw UTM transition artifact")
    l2_parser.add_argument("band_file", metavar="L1.utm.band", help="L1 .utm.band artifact")
    l2_parser.add_argument("--out-dir", required=True, metavar="DIR", help="directory for the emitted L2 artifacts")
    l2_parser.add_argument("--stem", metavar="NAME", help="artifact filename stem; defaults from the L1 band stem")

    run_parser = _add_command(sub, "run", help="Run a .tm program on a .utm.band artifact.")
    run_parser.add_argument("tm_file", metavar="HOST.tm", help="raw UTM transition artifact")
    run_parser.add_argument("input", metavar="INPUT.utm.band", help="encoded guest tape artifact")
    run_parser.add_argument("--max-steps", type=int, default=200_000, metavar="N", help="raw transition fuel; default: 200000")
    run_parser.add_argument("--view", choices=("decoded", "encoded", "raw"), default="decoded", help="run output view; default: decoded")
    run_parser.add_argument("--when", choices=("initial", "final"), default="final", help="show the selected view before or after running; default: final")
    run_parser.add_argument("--side", choices=("both", "left", "right"), default="both", help="encoded view side; default: both")
    run_parser.add_argument("--around-head", type=int, metavar="N", help="raw view: show addresses from HEAD-N through HEAD+N")
    run_parser.add_argument("--range", dest="raw_range", type=_parse_range, metavar="START:END", help="raw view: show an explicit inclusive address range")

    trace_parser = _add_command(sub, "trace", help="Emit a TSV trace for a .tm program and .utm.band input.")
    trace_parser.add_argument("tm_file", metavar="HOST.tm", help="raw UTM transition artifact")
    trace_parser.add_argument("band_file", metavar="INPUT.utm.band", help="encoded guest tape artifact")
    trace_parser.add_argument("--out", required=True, metavar="TRACE.tsv", help="trace TSV output path")
    trace_parser.add_argument("--level", choices=("raw", "instruction", "block", "source", "guest"), default="raw", help="trace grouping level")
    trace_parser.add_argument("--max-steps", type=int, default=100, metavar="N", help="maximum rows/groups to emit; default: 100")
    trace_parser.add_argument("--max-raw", type=int, metavar="N", help="raw transition guard; default: 100000, or 5000000 for source/guest")
    trace_parser.add_argument("--meta-out", metavar="TRACE.json", help="optional trace metadata sidecar")

    dbg_parser = _add_command(sub, "dbg", help="Start the MTM debugger REPL for a fixture or .tm/.utm.band pair.")
    dbg_parser.usage = "mtm dbg [-h] [--max-raw N] FIXTURE\n       mtm dbg [-h] [--max-raw N] HOST.tm INPUT.utm.band\n       mtm dbg [-h] --fixture FIXTURE [--max-raw N]"
    dbg_parser.add_argument("inputs", nargs="*", metavar="INPUT", help="fixture name, or HOST.tm INPUT.utm.band")
    dbg_parser.add_argument("--fixture", dest="fixture_name", metavar="FIXTURE", help="debug a built-in fixture by name")
    dbg_parser.add_argument("--max-raw", type=int, default=DEBUG_DEFAULT_MAX_RAW, metavar="N", help=f"raw transition guard for grouped debugger steps; default: {DEBUG_DEFAULT_MAX_RAW}")

    raw_argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(_normalize_range_args(list(raw_argv)))
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

    if args.command == "inspect":
        return _inspect(args)

    if args.command == "concepts":
        return _show_concepts(args)

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
        return _run_debugger_from_args(args)

    if args.command == "trace":
        return _write_trace(args)

    if args.input is None:
        raise SystemExit("run requires INPUT.utm.band")
    if args.raw_range is not None and args.around_head is not None:
        raise SystemExit("--range and --around-head are mutually exclusive")
    artifact = UTMBandArtifact.read(args.input)
    encoded_tape = artifact.to_encoded_tape()
    program_artifact = UTMProgramArtifact.read(args.tm_file)
    config = artifact.to_raw_instance(program_artifact)
    runtime_tape = dict(config.tape)
    result = program_artifact.run(artifact, fuel=args.max_steps)
    final_left_band, final_right_band = encoded_tape.left_band, encoded_tape.right_band
    if result["tape"] != runtime_tape:
        final_left_band, final_right_band = split_runtime_tape(result["tape"])
    final_encoded_tape = EncodedTape(
        encoded_tape.encoding,
        final_left_band,
        final_right_band,
        minimal_abi=encoded_tape.minimal_abi,
        target_abi=encoded_tape.target_abi,
    )
    initial_result = {
        "status": "initial",
        "state": config.state,
        "head": config.head,
        "steps": 0,
    }
    print(_select_run_view(
        args,
        initial_encoded_tape=encoded_tape,
        final_encoded_tape=final_encoded_tape,
        initial_result=initial_result,
        final_result=result,
        initial_runtime_tape=runtime_tape,
        final_runtime_tape=result["tape"],
        blank=program_artifact.program.blank,
    ))
    return 0


__all__ = ["main"]
