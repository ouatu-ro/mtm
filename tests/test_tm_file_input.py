from pathlib import Path

import pytest

from mtm.cli import main as cli_main
from examples.demo import main
from mtm.artifacts import read_tm, read_utm, read_utm_artifact, write_utm
from mtm.lowering import ACTIVE_RULE, lower_program_to_raw_tm
from mtm.meta_asm import build_universal_meta_asm
from mtm.source_file import load_python_tm, load_python_tm_instance
from mtm.raw_transition_tm import TMTransitionProgram
from mtm.semantic_objects import UTMBandArtifact, UTMProgramArtifact, encoded_band_from_utm_artifact, utm_artifact_from_band
from mtm.source_encoding import R, TMProgram


INCREMENTER_FILE = """\
blank = "_"
initial_state = "qFindMargin"
halt_state = "qDone"
input_string = "1011"
blanks_right = 4

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
    assert fixture.input_symbols == list("1011")
    assert fixture.initial_state == "qFindMargin"
    assert fixture.halt_state == "qDone"
    assert len(fixture.tm_program) == 6
    assert band.encoding.halt_state == "qDone"


def test_load_python_tm_file_requires_tm_program_object(tmp_path: Path) -> None:
    path = tmp_path / "raw_dict_tm.py"
    path.write_text("""\
initial_state = "q0"
halt_state = "qHalt"
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
    band, start_head = read_utm(utm_path)
    tm = UTMProgramArtifact.read(raw_tm_path, target_abi=artifact.target_abi, minimal_abi=artifact.minimal_abi)

    assert utm_path.exists()
    assert asm_path.exists()
    assert raw_tm_path.exists()
    assert artifact.to_encoded_band() == band
    assert start_head < 0
    assert tm.program.start_state == "START_STEP"
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
    tm = read_tm(raw_tm_path)
    assert tm.halt_state == "U_HALT"


def test_utm_artifact_roundtrip(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    fixture = load_python_tm(tm_path)
    band = fixture.build_band()
    utm_path = tmp_path / "incrementer.utm.band"

    write_utm(utm_path, utm_artifact_from_band(band))
    artifact = read_utm_artifact(utm_path)
    reconstructed_band = encoded_band_from_utm_artifact(artifact)
    compatibility_band, start_head = read_utm(utm_path)

    assert artifact.start_head < 0
    assert reconstructed_band.left_band == band.left_band
    assert reconstructed_band.right_band == band.right_band
    assert compatibility_band.left_band == band.left_band
    assert compatibility_band.right_band == band.right_band
    assert start_head == artifact.start_head


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


def test_primary_program_and_band_artifact_work_together(tmp_path: Path) -> None:
    tm_path = _write_tm_file(tmp_path)
    utm_path = tmp_path / "incrementer.utm.band"
    raw_tm_path = tmp_path / "utm.tm"

    assert cli_main(["compile", str(tm_path), "-o", str(utm_path), "--tm-out", str(raw_tm_path)]) == 0

    band_artifact = UTMBandArtifact.read(utm_path)
    program_artifact = UTMProgramArtifact.read(
        raw_tm_path,
        target_abi=band_artifact.target_abi,
        minimal_abi=band_artifact.minimal_abi,
    )
    result = program_artifact.run(band_artifact, fuel=200_000)

    assert result["status"] == "halted"
    assert result["state"] == "U_HALT"
