from __future__ import annotations

from types import SimpleNamespace

from mtm import cli
import mtm
import mtm.debugger
import mtm.debugger.session
import mtm.debugger.shell
import mtm.debugger.trace
import mtm.lowering
import mtm.meta_asm
import mtm.semantic_objects


COMPACT_STARTUP = """\
status: running raw_step=0 max_raw=100000 history=0/0
snapshot: state='START_STEP' head=-155 read='#CUR_STATE'
where: block=START_STEP instruction=setup routine=0:seek op=0
instruction: SEEK #CUR_STATE L"""

FULL_VIEW_MARKER = "raw tape: <full-view>"


def _install_debugger_stubs(monkeypatch):
    calls = {
        "load_fixture": [],
        "build_band": [],
        "build_universal": [],
        "lower_with_source_map": [],
        "start_head": [],
        "runner_inits": [],
        "session_inits": [],
        "session_status_calls": 0,
        "session_view_calls": 0,
        "shell_inits": 0,
        "shell_cmdloop_calls": [],
        "shell_cmdloop_intro": [],
    }

    fake_band = SimpleNamespace(
        encoding="encoding",
        runtime_tape={0: "0"},
        linear=lambda: ("0", "1"),
    )

    class FakeFixture:
        name = "incrementer"

        def build_band(self):
            calls["build_band"].append(self.name)
            return fake_band

    class FakeRawTraceRunner:
        def __init__(self, *args, **kwargs):
            calls["runner_inits"].append((len(args), tuple(sorted(kwargs))))

    class FakeDebuggerSession:
        def __init__(self, *args, **kwargs):
            calls["session_inits"].append((len(args), tuple(sorted(kwargs))))

        def status_text(self) -> str:
            calls["session_status_calls"] += 1
            return COMPACT_STARTUP

        def view_text(self) -> str:
            calls["session_view_calls"] += 1
            return FULL_VIEW_MARKER

    class FakeDebuggerShell:
        prompt = "mtmdbg> "

        def __init__(self, session, *args, **kwargs):
            calls["shell_inits"] += 1
            self.session = session

        def cmdloop(self, intro=None):
            calls["shell_cmdloop_calls"].append(1)
            calls["shell_cmdloop_intro"].append(intro)

    def fake_load_fixture(name: str):
        calls["load_fixture"].append(name)
        return FakeFixture()

    def fake_build_universal_meta_asm(encoding):
        calls["build_universal"].append(encoding)
        return SimpleNamespace(entry_label="START_STEP")

    def fake_lower_program_with_source_map(program, alphabet):
        calls["lower_with_source_map"].append((program.entry_label, len(tuple(alphabet))))
        return SimpleNamespace(raw_program="raw-program", source_map="source-map")

    def fake_start_head_from_encoded_band(band):
        calls["start_head"].append(band is fake_band)
        return -155

    monkeypatch.setattr(cli, "load_fixture", fake_load_fixture, raising=False)
    monkeypatch.setattr(mtm, "load_fixture", fake_load_fixture, raising=False)
    monkeypatch.setattr(mtm.lowering, "lower_program_with_source_map", fake_lower_program_with_source_map, raising=False)
    monkeypatch.setattr(mtm.meta_asm, "build_universal_meta_asm", fake_build_universal_meta_asm, raising=False)
    monkeypatch.setattr(mtm.semantic_objects, "start_head_from_encoded_band", fake_start_head_from_encoded_band, raising=False)
    monkeypatch.setattr(mtm.debugger, "RawTraceRunner", FakeRawTraceRunner, raising=False)
    monkeypatch.setattr(mtm.debugger, "DebuggerSession", FakeDebuggerSession, raising=False)
    monkeypatch.setattr(mtm.debugger, "DebuggerShell", FakeDebuggerShell, raising=False)
    monkeypatch.setattr(mtm.debugger.session, "DebuggerSession", FakeDebuggerSession, raising=False)
    monkeypatch.setattr(mtm.debugger.shell, "DebuggerShell", FakeDebuggerShell, raising=False)
    monkeypatch.setattr(mtm.debugger.trace, "RawTraceRunner", FakeRawTraceRunner, raising=False)
    monkeypatch.setattr(cli, "lower_program_with_source_map", fake_lower_program_with_source_map, raising=False)
    monkeypatch.setattr(cli, "build_universal_meta_asm", fake_build_universal_meta_asm, raising=False)
    monkeypatch.setattr(cli, "start_head_from_encoded_band", fake_start_head_from_encoded_band, raising=False)
    monkeypatch.setattr(cli, "RawTraceRunner", FakeRawTraceRunner, raising=False)
    monkeypatch.setattr(cli, "DebuggerSession", FakeDebuggerSession, raising=False)
    monkeypatch.setattr(cli, "DebuggerShell", FakeDebuggerShell, raising=False)

    return calls


def _run_dbg(args: list[str], monkeypatch, capsys):
    calls = _install_debugger_stubs(monkeypatch)
    exit_code = cli.main(args)
    output = capsys.readouterr().out
    return exit_code, output, calls


def test_cli_dbg_positional_fixture_starts_compact_debugger_session(monkeypatch, capsys):
    exit_code, output, calls = _run_dbg(["dbg", "incrementer"], monkeypatch, capsys)

    assert exit_code == 0
    assert "mtm debugger: fixture incrementer" in output
    assert "type `help` for commands" in output
    assert "status: running raw_step=0 max_raw=100000 history=0/0" in output
    assert "snapshot: state='START_STEP' head=-155 read='#CUR_STATE'" in output
    assert "where: block=START_STEP instruction=setup routine=0:seek op=0" in output
    assert FULL_VIEW_MARKER not in output
    assert calls["session_status_calls"] == 1
    assert calls["session_view_calls"] == 0
    assert calls["shell_inits"] == 1
    assert len(calls["shell_cmdloop_calls"]) == 1


def test_cli_dbg_flag_and_positional_share_fixture_path(monkeypatch, capsys):
    positional_code, positional_output, positional_calls = _run_dbg(["dbg", "incrementer"], monkeypatch, capsys)
    flag_code, flag_output, flag_calls = _run_dbg(["dbg", "--fixture", "incrementer"], monkeypatch, capsys)

    assert positional_code == 0
    assert flag_code == 0
    assert "mtm debugger: fixture incrementer" in positional_output
    assert "mtm debugger: fixture incrementer" in flag_output
    assert positional_calls["load_fixture"] == ["incrementer"]
    assert flag_calls["load_fixture"] == ["incrementer"]
    assert positional_calls["build_band"] == ["incrementer"]
    assert flag_calls["build_band"] == ["incrementer"]
    assert positional_calls["build_universal"] == ["encoding"]
    assert flag_calls["build_universal"] == ["encoding"]
    assert positional_calls["lower_with_source_map"] == [("START_STEP", 3)]
    assert flag_calls["lower_with_source_map"] == [("START_STEP", 3)]
    assert positional_calls["start_head"] == [True]
    assert flag_calls["start_head"] == [True]
    assert positional_calls["runner_inits"] == flag_calls["runner_inits"]
    assert positional_calls["session_inits"] == flag_calls["session_inits"]
    assert positional_calls["shell_inits"] == 1
    assert flag_calls["shell_inits"] == 1
    assert len(positional_calls["shell_cmdloop_calls"]) == 1
    assert len(flag_calls["shell_cmdloop_calls"]) == 1
