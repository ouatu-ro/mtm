from pathlib import Path

import pytest

from mtm.cli import main as cli_main
from examples.demo import main
from mtm.artifacts import read_source_artifact, read_utm_artifact
from mtm.lowering import ACTIVE_RULE, lower_program_to_raw_tm
from mtm.meta_asm import build_universal_meta_asm
from mtm.source_file import load_python_tm, load_python_tm_instance, source_artifact_from_python
from mtm.raw_transition_tm import TMTransitionProgram
from mtm.semantic_objects import TMBand, UTMBandArtifact, UTMProgramArtifact, encoded_band_from_utm_artifact, utm_artifact_from_band
from mtm.source_encoding import R, TMAbi, TMProgram


INCREMENTER_FILE = """\
blank = "_"
initial_state = "qFindMargin"
halt_state = "qDone"
band = TMBand(right_band=tuple("1011____"), head=0, blank=blank)

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
    band = fixture.build_band()

    assert fixture.name == "incrementer_tm"
    assert isinstance(fixture.tm_program, TMProgram)
    assert fixture.band == TMBand(right_band=tuple("1011____"), head=0, blank="_")
    assert fixture.initial_state == "qFindMargin"
    assert fixture.halt_state == "qDone"
    assert len(fixture.tm_program) == 6
    assert band.encoding.halt_state == "qDone"


def test_load_python_tm_file_requires_tm_program_object(tmp_path: Path) -> None:
    path = tmp_path / "raw_dict_tm.py"
    path.write_text("""\
initial_state = "q0"
halt_state = "qHalt"
band = TMBand(right_band=("_",), head=0, blank="_")
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
    assert instance.band.blank == "_"
    assert instance.band.head == 0
    assert instance.band.cells[:4] == tuple("1011")


def test_source_artifact_from_python_round_trips_without_execution(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    source_path = tmp_path / "incrementer.mtm.source"

    source_artifact_from_python(tm_path).write(source_path)
    loaded = read_source_artifact(source_path)

    assert loaded.name == "incrementer_tm"
    assert loaded.initial_state == "qFindMargin"
    assert loaded.halt_state == "qDone"
    assert loaded.program == load_python_tm(tm_path).tm_program
    assert loaded.band == TMBand(right_band=tuple("1011____"), head=0, blank="_")


def test_source_artifact_reader_rejects_executable_code(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    source_path = tmp_path / "evil.mtm.source"
    source_path.write_text(f"""\
format = 'mtm-source-v1'
tm_program = __import__('pathlib').Path({str(marker)!r}).write_text('bad')
band = {{}}
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
    band = artifact.to_encoded_band()
    tm = UTMProgramArtifact.read(raw_tm_path)

    assert utm_path.exists()
    assert asm_path.exists()
    assert raw_tm_path.exists()
    assert artifact.to_encoded_band() == band
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
    assert cli_main(["emit-tm", "examples/incrementer_tm.py", "-o", str(raw_tm_path)]) == 0
    tm = TMTransitionProgram.read(raw_tm_path)
    assert tm.halt_state == "U_HALT"


def test_cli_emit_source_from_example_file(tmp_path: Path) -> None:
    source_path = tmp_path / "incrementer.mtm.source"

    assert cli_main(["emit-source", "examples/incrementer_tm.py", "-o", str(source_path)]) == 0
    loaded = read_source_artifact(source_path)

    assert loaded.name == "incrementer_tm"
    assert loaded.initial_state == "qFindMargin"
    assert loaded.halt_state == "qDone"
    assert len(loaded.program) == 6


def test_utm_artifact_roundtrip(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    fixture = load_python_tm(tm_path)
    band = fixture.build_band()
    utm_path = tmp_path / "incrementer.utm.band"

    utm_artifact_from_band(band).write(utm_path)
    artifact = read_utm_artifact(utm_path)
    reconstructed_band = encoded_band_from_utm_artifact(artifact)

    assert artifact.start_head < 0
    assert reconstructed_band.left_band == band.left_band
    assert reconstructed_band.right_band == band.right_band


def test_primary_program_and_band_artifact_readers(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    fixture = load_python_tm(tm_path)
    band = fixture.build_band()
    utm_path = tmp_path / "incrementer.utm.band"
    raw_tm_path = tmp_path / "utm.tm"

    utm_artifact_from_band(band).write(utm_path)
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    lower_program_to_raw_tm(program, alphabet).write(raw_tm_path)

    artifact = UTMBandArtifact.read(utm_path)
    tm = TMTransitionProgram.read(raw_tm_path)

    assert artifact.to_encoded_band() == band
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


def test_cli_run_preserves_program_side_abi_metadata(tmp_path: Path) -> None:
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

    assert cli_main(["l1", "examples/incrementer_tm.py", "--out-dir", str(out_dir)]) == 0

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

    assert cli_main(["l1", "examples/incrementer_tm.py", "--out-dir", str(out_dir), "--stem", "incrementer"]) == 0
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
