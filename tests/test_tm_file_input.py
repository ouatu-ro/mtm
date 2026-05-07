import json
from pathlib import Path

import pytest

from mtm.cli import main as cli_main
from examples.demo import main
from mtm.artifacts import read_source_artifact, read_utm_artifact
from mtm.lowering import ACTIVE_RULE, lower_program_to_raw_tm
from mtm.meta_asm import build_universal_meta_asm
from mtm.source_file import load_python_tm, load_python_tm_instance, source_artifact_from_python
from mtm.raw_transition_tm import TMTransitionProgram
from mtm.semantic_objects import SourceTape, UTMBandArtifact, UTMProgramArtifact, decoded_view_from_encoded_tape, encoded_tape_from_utm_artifact, utm_artifact_from_tape
from mtm.source_encoding import R, TMAbi, TMProgram


INCREMENTER_FILE = """\
blank = "_"
initial_state = "qFindMargin"
halt_state = "qDone"
tape = SourceTape(right_band=tuple("1011____"), head=0, blank=blank)

tm_program = TMProgram({
    ("qFindMargin", "0"): ("qFindMargin", "0", R),
    ("qFindMargin", "1"): ("qFindMargin", "1", R),
    ("qFindMargin", blank): ("qAdd", blank, L),
    ("qAdd", "0"): ("qDone", "1", L),
    ("qAdd", "1"): ("qAdd", "0", L),
    ("qAdd", blank): ("qDone", "1", L),
}, initial_state=initial_state, halt_state=halt_state, blank=blank)
"""


def _write_tm_file(tmp_path: Path) -> Path:
    path = tmp_path / "incrementer_tm.py"
    path.write_text(INCREMENTER_FILE)
    return path


def test_load_python_tm_file(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    fixture = load_python_tm(tm_path)
    tape = fixture.build_encoded_tape()

    assert fixture.name == "incrementer_tm"
    assert isinstance(fixture.tm_program, TMProgram)
    assert fixture.tape == SourceTape(right_band=tuple("1011____"), head=0, blank="_")
    assert fixture.initial_state == "qFindMargin"
    assert fixture.halt_state == "qDone"
    assert len(fixture.tm_program) == 6
    assert tape.encoding.halt_state == "qDone"


def test_load_python_tm_file_requires_tm_program_object(tmp_path: Path) -> None:
    path = tmp_path / "raw_dict_tm.py"
    path.write_text("""\
initial_state = "q0"
halt_state = "qHalt"
tape = SourceTape(right_band=("_",), head=0, blank="_")
tm_program = {("q0", "_"): ("qHalt", "_", R)}
""")

    with pytest.raises(TypeError, match="tm_program.*TMProgram"):
        load_python_tm(path)


def test_load_python_tm_instance(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    instance = load_python_tm_instance(tm_path)

    assert instance.program[("qFindMargin", "0")] == ("qFindMargin", "0", R)
    assert instance.initial_state == "qFindMargin"
    assert instance.halt_state == "qDone"
    assert instance.tape.blank == "_"
    assert instance.tape.head == 0
    assert instance.tape.cells[:4] == tuple("1011")


def test_source_artifact_from_python_round_trips_without_execution(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    source_path = tmp_path / "incrementer.mtm.source"

    source_artifact_from_python(tm_path).write(source_path)
    loaded = read_source_artifact(source_path)

    assert loaded.name == "incrementer_tm"
    assert loaded.initial_state == "qFindMargin"
    assert loaded.halt_state == "qDone"
    assert loaded.program == load_python_tm(tm_path).tm_program
    assert loaded.tape == SourceTape(right_band=tuple("1011____"), head=0, blank="_")


def test_source_artifact_reader_rejects_executable_code(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    source_path = tmp_path / "evil.mtm.source"
    source_path.write_text(f"""\
format = 'mtm-source-v1'
tm_program = __import__('pathlib').Path({str(marker)!r}).write_text('bad')
tape = {{}}
initial_state = 'start'
halt_state = 'halt'
""")

    with pytest.raises(ValueError, match="tm_program.*literal"):
        read_source_artifact(source_path)

    assert not marker.exists()


def test_demo_tm_file_emit_and_run(tmp_path: Path, capsys) -> None:
    tm_path = _write_tm_file(tmp_path)
    exit_code = main(["--tm-file", str(tm_path), "--emit-raw-tm", "--run-utm"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "RAW UTM" in output
    assert "raw_tm = {" in output
    assert "RAW UTM RESULT" in output
    assert "FINAL STATUS: halted" in output
    assert "1 1 0 0 _ _ _ _" in output


def test_cli_compile_emit_and_run_pipeline(tmp_path: Path, capsys) -> None:
    tm_path = _write_tm_file(tmp_path)
    utm_path = tmp_path / "incrementer.utm.band"
    asm_path = tmp_path / "utm.asm"
    raw_tm_path = tmp_path / "utm.tm"

    assert cli_main(["compile", str(tm_path), "-o", str(utm_path), "--asm-out", str(asm_path), "--tm-out", str(raw_tm_path)]) == 0
    artifact = read_utm_artifact(utm_path)
    tape = artifact.to_encoded_tape()
    tm = UTMProgramArtifact.read(raw_tm_path)

    assert utm_path.exists()
    assert asm_path.exists()
    assert raw_tm_path.exists()
    assert artifact.to_encoded_tape() == tape
    assert artifact.start_head < 0
    assert tm.program.start_state == "START_STEP"
    assert tm.target_abi == artifact.target_abi
    assert tm.minimal_abi == artifact.minimal_abi
    assert "LABEL START_STEP" in asm_path.read_text()

    assert cli_main(["run", str(raw_tm_path), str(utm_path)]) == 0
    output = capsys.readouterr().out
    assert "FINAL STATUS: halted" in output
    assert "1 1 0 0 _ _ _ _" in output


def test_cli_compile_with_explicit_target_abi(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    utm_path = tmp_path / "incrementer.utm.band"

    assert cli_main([
        "compile",
        str(tm_path),
        "-o",
        str(utm_path),
        "--state-width",
        "3",
        "--symbol-width",
        "4",
        "--dir-width",
        "2",
    ]) == 0

    artifact = read_utm_artifact(utm_path)
    assert artifact.minimal_abi.state_width == 2
    assert artifact.minimal_abi.symbol_width == 2
    assert artifact.minimal_abi.dir_width == 1
    assert artifact.target_abi.state_width == 3
    assert artifact.target_abi.symbol_width == 4
    assert artifact.target_abi.dir_width == 2


def test_cli_emit_tm_from_example_file(tmp_path: Path) -> None:
    raw_tm_path = tmp_path / "utm.tm"
    assert cli_main(["emit-tm", "examples/source/incrementer_tm.py", "-o", str(raw_tm_path)]) == 0
    tm = TMTransitionProgram.read(raw_tm_path)
    assert tm.halt_state == "U_HALT"


def test_cli_emit_source_from_example_file(tmp_path: Path) -> None:
    source_path = tmp_path / "incrementer.mtm.source"

    assert cli_main(["emit-source", "examples/source/incrementer_tm.py", "-o", str(source_path)]) == 0
    loaded = read_source_artifact(source_path)

    assert loaded.name == "incrementer_tm"
    assert loaded.initial_state == "qFindMargin"
    assert loaded.halt_state == "qDone"
    assert len(loaded.program) == 6


def test_utm_artifact_roundtrip(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    fixture = load_python_tm(tm_path)
    tape = fixture.build_encoded_tape()
    utm_path = tmp_path / "incrementer.utm.band"

    utm_artifact_from_tape(tape).write(utm_path)
    artifact = read_utm_artifact(utm_path)
    reconstructed_band = encoded_tape_from_utm_artifact(artifact)

    assert artifact.start_head < 0
    assert reconstructed_band.left_band == tape.left_band
    assert reconstructed_band.right_band == tape.right_band


def test_primary_program_and_band_artifact_readers(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    fixture = load_python_tm(tm_path)
    tape = fixture.build_encoded_tape()
    utm_path = tmp_path / "incrementer.utm.band"
    raw_tm_path = tmp_path / "utm.tm"

    utm_artifact_from_tape(tape).write(utm_path)
    program = build_universal_meta_asm(tape.encoding)
    alphabet = sorted(set(tape.linear()) | {"0", "1", ACTIVE_RULE})
    lower_program_to_raw_tm(program, alphabet).write(raw_tm_path)

    artifact = UTMBandArtifact.read(utm_path)
    tm = TMTransitionProgram.read(raw_tm_path)

    assert artifact.to_encoded_tape() == tape
    assert tm.start_state == "START_STEP"


def test_raw_tm_artifact_reader_rejects_executable_code(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    raw_tm_path = tmp_path / "evil.tm"
    raw_tm_path.write_text(f"""\
format = 'mtm-raw-tm-v1'
start_state = __import__('pathlib').Path({str(marker)!r}).write_text('bad')
halt_state = 'halt'
blank = '_RUNTIME_BLANK'
alphabet = ['_RUNTIME_BLANK']
raw_tm = {{}}
""")

    with pytest.raises(ValueError, match="start_state.*literal"):
        TMTransitionProgram.read(raw_tm_path)

    assert not marker.exists()


def test_utm_band_artifact_reader_rejects_executable_code(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    utm_path = tmp_path / "evil.utm.band"
    utm_path.write_text(f"""\
format = 'mtm-utm-band-v1'
start_head = 0
encoding = __import__('pathlib').Path({str(marker)!r}).write_text('bad')
left_band = []
right_band = []
target_abi = {{}}
minimal_abi = {{}}
""")

    with pytest.raises(ValueError, match="encoding.*literal"):
        UTMBandArtifact.read(utm_path)

    assert not marker.exists()


def test_artifact_readers_validate_format(tmp_path: Path) -> None:
    raw_tm_path = tmp_path / "wrong.tm"
    raw_tm_path.write_text("format = 'not-mtm'\n")

    with pytest.raises(ValueError, match="unsupported artifact format"):
        TMTransitionProgram.read(raw_tm_path)


def test_primary_program_and_band_artifact_work_together(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    utm_path = tmp_path / "incrementer.utm.band"
    raw_tm_path = tmp_path / "utm.tm"

    assert cli_main(["compile", str(tm_path), "-o", str(utm_path), "--tm-out", str(raw_tm_path)]) == 0

    band_artifact = UTMBandArtifact.read(utm_path)
    program_artifact = UTMProgramArtifact.read(raw_tm_path)
    result = program_artifact.run(band_artifact, fuel=200_000)

    assert program_artifact.target_abi == band_artifact.target_abi
    assert program_artifact.minimal_abi == band_artifact.minimal_abi
    assert result["status"] == "halted"
    assert result["state"] == "U_HALT"


def test_cli_run_preserves_program_side_abi_metadata(tmp_path: Path, capsys) -> None:
    tm_path = _write_tm_file(tmp_path)
    utm_path = tmp_path / "incrementer.utm.band"
    raw_tm_path = tmp_path / "utm.tm"

    assert cli_main(["compile", str(tm_path), "-o", str(utm_path), "--tm-out", str(raw_tm_path)]) == 0
    band_artifact = UTMBandArtifact.read(utm_path)
    program_artifact = UTMProgramArtifact.read(raw_tm_path)
    mismatched = UTMProgramArtifact(
        program=program_artifact.program,
        target_abi=TMAbi(
            band_artifact.target_abi.state_width + 1,
            band_artifact.target_abi.symbol_width,
            band_artifact.target_abi.dir_width,
            band_artifact.target_abi.grammar_version,
            "mismatched",
        ),
        minimal_abi=program_artifact.minimal_abi,
    )
    mismatched.write(raw_tm_path)

    assert cli_main(["run", str(raw_tm_path), str(utm_path)]) == 0
    output = capsys.readouterr().out
    assert "FINAL STATUS: halted" in output
    assert "FINAL STATE: U_HALT" in output


def test_cli_run_rejects_program_abi_narrower_than_band(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    utm_path = tmp_path / "incrementer.utm.band"
    raw_tm_path = tmp_path / "utm.tm"

    assert cli_main([
        "compile",
        str(tm_path),
        "-o",
        str(utm_path),
        "--tm-out",
        str(raw_tm_path),
        "--state-width",
        "3",
        "--symbol-width",
        "4",
        "--dir-width",
        "2",
    ]) == 0
    band_artifact = UTMBandArtifact.read(utm_path)
    program_artifact = UTMProgramArtifact.read(raw_tm_path)
    mismatched = UTMProgramArtifact(
        program=program_artifact.program,
        target_abi=TMAbi(
            band_artifact.target_abi.state_width - 1,
            band_artifact.target_abi.symbol_width,
            band_artifact.target_abi.dir_width,
            band_artifact.target_abi.grammar_version,
            "narrower",
        ),
        minimal_abi=program_artifact.minimal_abi,
    )
    mismatched.write(raw_tm_path)

    with pytest.raises(ValueError, match="ABI mismatch"):
        cli_main(["run", str(raw_tm_path), str(utm_path)])


def test_cli_run_allows_old_tm_without_abi_metadata(tmp_path: Path, capsys) -> None:
    tm_path = _write_tm_file(tmp_path)
    utm_path = tmp_path / "incrementer.utm.band"
    raw_tm_path = tmp_path / "utm.tm"

    assert cli_main(["compile", str(tm_path), "-o", str(utm_path), "--tm-out", str(raw_tm_path)]) == 0
    raw_tm = UTMProgramArtifact.read(raw_tm_path).program
    raw_tm.write(raw_tm_path)

    assert UTMProgramArtifact.read(raw_tm_path).target_abi is None
    assert cli_main(["run", str(raw_tm_path), str(utm_path)]) == 0
    output = capsys.readouterr().out
    assert "FINAL STATUS: halted" in output


def test_cli_l1_generates_level_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "artifacts"

    assert cli_main(["l1", "examples/source/incrementer_tm.py", "--out-dir", str(out_dir)]) == 0

    source_path = out_dir / "incrementer_tm.mtm.source"
    band_path = out_dir / "incrementer_tm.l1.utm.band"
    tm_path = out_dir / "incrementer_tm.l1.tm"

    assert read_source_artifact(source_path).name == "incrementer_tm"
    band = UTMBandArtifact.read(band_path)
    program = UTMProgramArtifact.read(tm_path)
    assert band.target_abi == program.target_abi
    assert program.program.start_state == "START_STEP"


def test_cli_l2_generates_artifacts_and_runs_for_bounded_fuel(tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "artifacts"

    assert cli_main(["l1", "examples/source/incrementer_tm.py", "--out-dir", str(out_dir), "--stem", "incrementer"]) == 0
    assert cli_main([
        "l2",
        str(out_dir / "incrementer.l1.tm"),
        str(out_dir / "incrementer.l1.utm.band"),
        "--out-dir",
        str(out_dir),
        "--stem",
        "incrementer",
    ]) == 0

    band_path = out_dir / "incrementer.l2.utm.band"
    tm_path = out_dir / "incrementer.l2.tm"
    band = UTMBandArtifact.read(band_path)
    program = UTMProgramArtifact.read(tm_path)

    assert band.target_abi == program.target_abi
    assert band.encoding.initial_state == "START_STEP"
    assert cli_main(["run", str(tm_path), str(band_path), "--max-steps", "1"]) == 0
    output = capsys.readouterr().out
    assert "FINAL STATUS: fuel_exhausted" in output


def test_cli_l2_from_wider_l1_abi_generates_coherent_band(tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "artifacts"
    l1_target = TMAbi(3, 3, 2, "mtm-v1", "U[Wq=3,Ws=3,Wd=2]")

    assert cli_main([
        "l1",
        "examples/source/incrementer_tm.py",
        "--out-dir",
        str(out_dir),
        "--stem",
        "incrementer-wide",
        "--state-width",
        str(l1_target.state_width),
        "--symbol-width",
        str(l1_target.symbol_width),
        "--dir-width",
        str(l1_target.dir_width),
    ]) == 0
    assert cli_main([
        "l2",
        str(out_dir / "incrementer-wide.l1.tm"),
        str(out_dir / "incrementer-wide.l1.utm.band"),
        "--out-dir",
        str(out_dir),
        "--stem",
        "incrementer-wide",
    ]) == 0

    l1_band = UTMBandArtifact.read(out_dir / "incrementer-wide.l1.utm.band")
    l1_program = UTMProgramArtifact.read(out_dir / "incrementer-wide.l1.tm")
    l2_band = UTMBandArtifact.read(out_dir / "incrementer-wide.l2.utm.band")
    l2_program = UTMProgramArtifact.read(out_dir / "incrementer-wide.l2.tm")
    l2_view = decoded_view_from_encoded_tape(l2_band.to_encoded_tape())

    assert l1_band.minimal_abi == TMAbi(2, 2, 1, "mtm-v1", "min[Wq=2,Ws=2,Wd=1]")
    assert l1_band.target_abi == l1_target
    assert l1_program.target_abi == l1_target
    assert l2_band.target_abi == l2_program.target_abi
    assert l2_band.target_abi != l1_target
    assert l2_band.target_abi.family_label.startswith("raw-min[")
    assert l2_view.current_state == "START_STEP"
    assert l2_view.simulated_tape.head == l1_band.start_head

    assert cli_main([
        "run",
        str(out_dir / "incrementer-wide.l2.tm"),
        str(out_dir / "incrementer-wide.l2.utm.band"),
        "--max-steps",
        "1",
    ]) == 0
    output = capsys.readouterr().out
    assert "FINAL STATUS: fuel_exhausted" in output


def test_cli_trace_emits_raw_instruction_and_block_levels(tmp_path: Path) -> None:
    out_dir = tmp_path / "artifacts"

    assert cli_main(["l1", "examples/source/incrementer_tm.py", "--out-dir", str(out_dir), "--stem", "incrementer"]) == 0

    tm_path = out_dir / "incrementer.l1.tm"
    band_path = out_dir / "incrementer.l1.utm.band"
    raw_trace = out_dir / "raw.tsv"
    raw_meta = out_dir / "raw.json"
    instruction_trace = out_dir / "instruction.tsv"
    block_trace = out_dir / "block.tsv"

    assert cli_main([
        "trace",
        str(tm_path),
        str(band_path),
        "--level",
        "raw",
        "--max-steps",
        "3",
        "--out",
        str(raw_trace),
        "--meta-out",
        str(raw_meta),
    ]) == 0
    raw_lines = raw_trace.read_text().splitlines()
    assert raw_lines[0].startswith("step\tstatus\tstate\tread\twrite\tmove\tnext_state")
    assert len(raw_lines) == 4
    assert "\tSTART_STEP\t" in raw_lines[1]
    raw_meta_data = json.loads(raw_meta.read_text())
    assert raw_meta_data["format"] == "mtm-trace-meta-v1"
    assert raw_meta_data["level"] == "raw"
    assert raw_meta_data["initial_state"] == "START_STEP"
    assert isinstance(raw_meta_data["initial_head"], int)
    assert str(raw_meta_data["initial_head"]) in raw_meta_data["initial_tape"]
    assert raw_meta_data["initial_tape"][str(raw_meta_data["initial_head"])] == "#CUR_STATE"

    assert cli_main([
        "trace",
        str(tm_path),
        str(band_path),
        "--level",
        "instruction",
        "--max-steps",
        "2",
        "--out",
        str(instruction_trace),
    ]) == 0
    instruction_lines = instruction_trace.read_text().splitlines()
    assert instruction_lines[0].startswith("group\tstatus\traw_start\traw_end\traw_delta")
    assert len(instruction_lines) == 3
    assert "\tSTART_STEP\t0\t0\tcompare_global_global\t" in instruction_lines[1]

    assert cli_main([
        "trace",
        str(tm_path),
        str(band_path),
        "--level",
        "block",
        "--max-steps",
        "1",
        "--out",
        str(block_trace),
    ]) == 0
    block_lines = block_trace.read_text().splitlines()
    assert block_lines[0].startswith("group\tstatus\traw_start\traw_end\traw_delta")
    assert len(block_lines) == 2
    assert "\tSTART_STEP\t0\t0\tcompare_global_global\t" in block_lines[1]

    source_trace = out_dir / "source.tsv"
    assert cli_main([
        "trace",
        str(tm_path),
        str(band_path),
        "--level",
        "source",
        "--max-steps",
        "2",
        "--out",
        str(source_trace),
    ]) == 0
    source_lines = source_trace.read_text().splitlines()
    assert source_lines[0].startswith(
        "group\tstatus\traw_start\traw_end\traw_delta\tstate\tread\twrite\tmove\tnext_state\thead_before\thead_after"
    )
    assert len(source_lines) == 3
    first_source_step = source_lines[1].split("\t")
    assert first_source_step[1] == "stepped"
    assert first_source_step[5:12] == ["qFindMargin", "1", "1", "1", "qFindMargin", "0", "1"]
    assert "\tSTART_STEP\t0\t0\tcompare_global_global\t" in source_lines[1]
    second_source_step = source_lines[2].split("\t")
    assert second_source_step[1] == "stepped"
    assert second_source_step[5:12] == ["qFindMargin", "0", "0", "1", "qFindMargin", "1", "2"]
    assert "\tSTART_STEP\t0\t0\tcompare_global_global\t" in source_lines[2]
