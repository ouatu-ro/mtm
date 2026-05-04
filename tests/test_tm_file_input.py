from pathlib import Path

from mtm.demo import main
from mtm.program_input import load_python_tm


INCREMENTER_FILE = """\
blank = "_"
initial_state = "qFindMargin"
halt_state = "qDone"
input_string = "1011"
blanks_right = 4

tm_program = {
    ("qFindMargin", "0"): ("qFindMargin", "0", R),
    ("qFindMargin", "1"): ("qFindMargin", "1", R),
    ("qFindMargin", blank): ("qAdd", blank, L),
    ("qAdd", "0"): ("qDone", "1", L),
    ("qAdd", "1"): ("qAdd", "0", L),
    ("qAdd", blank): ("qDone", "1", L),
}
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
    assert fixture.input_symbols == list("1011")
    assert fixture.initial_state == "qFindMargin"
    assert fixture.halt_state == "qDone"
    assert len(fixture.tm_program) == 6
    assert band.encoding.halt_state == "qDone"


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
