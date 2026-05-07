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


def _install_debugger_stubs(monkeypatch):
    calls = {
        "load_fixture": [],
        "build_tape": [],
        "build_universal": [],
        "lower_with_source_map": [],
        "start_head": [],
        "runner_inits": [],
        "session_inits": [],
        "shell_inits": 0,
        "startup_calls": [],
        "shell_cmdloop_calls": [],
    }

    fake_band = SimpleNamespace(
        encoding="encoding",
        runtime_tape={0: "0"},
        linear=lambda: ("0", "1"),
    )

    class FakeFixture:
        name = "incrementer"

        def build_tape(self):
            calls["build_tape"].append(self.name)
            return fake_band

    class FakeRawTraceRunner:
        def __init__(self, *args, **kwargs):
            calls["runner_inits"].append((len(args), tuple(sorted(kwargs))))

    class FakeDebuggerSession:
        def __init__(self, *args, **kwargs):
            calls["session_inits"].append((len(args), tuple(sorted(kwargs))))

    class FakeDebuggerShell:
        prompt = "mtmdbg> "

        def __init__(self, session, *args, **kwargs):
            calls["shell_inits"] += 1
            self.session = session

        def render_startup(self, fixture_name: str) -> str:
            calls["startup_calls"].append(fixture_name)
            return f"startup:{fixture_name}"

        def cmdloop(self, intro=None):
            calls["shell_cmdloop_calls"].append(intro)

        def format_output(self, text: str) -> str:
            return f"formatted:{text}"

    def fake_load_fixture(name: str):
        calls["load_fixture"].append(name)
        return FakeFixture()

    def fake_build_universal_meta_asm(encoding):
        calls["build_universal"].append(encoding)
        return SimpleNamespace(entry_label="START_STEP")

    def fake_lower_program_with_source_map(program, alphabet):
        calls["lower_with_source_map"].append((program.entry_label, len(tuple(alphabet))))
        return SimpleNamespace(raw_program="raw-program", source_map="source-map")

    def fake_start_head_from_encoded_tape(band):
        calls["start_head"].append(band is fake_band)
        return -155

    monkeypatch.setattr(cli, "load_fixture", fake_load_fixture, raising=False)
    monkeypatch.setattr(mtm, "load_fixture", fake_load_fixture, raising=False)
    monkeypatch.setattr(mtm.lowering, "lower_program_with_source_map", fake_lower_program_with_source_map, raising=False)
    monkeypatch.setattr(mtm.meta_asm, "build_universal_meta_asm", fake_build_universal_meta_asm, raising=False)
    monkeypatch.setattr(mtm.semantic_objects, "start_head_from_encoded_tape", fake_start_head_from_encoded_tape, raising=False)
    monkeypatch.setattr(mtm.debugger, "RawTraceRunner", FakeRawTraceRunner, raising=False)
    monkeypatch.setattr(mtm.debugger, "DebuggerSession", FakeDebuggerSession, raising=False)
    monkeypatch.setattr(mtm.debugger, "DebuggerShell", FakeDebuggerShell, raising=False)
    monkeypatch.setattr(mtm.debugger.session, "DebuggerSession", FakeDebuggerSession, raising=False)
    monkeypatch.setattr(mtm.debugger.shell, "DebuggerShell", FakeDebuggerShell, raising=False)
    monkeypatch.setattr(mtm.debugger.trace, "RawTraceRunner", FakeRawTraceRunner, raising=False)
    monkeypatch.setattr(cli, "lower_program_with_source_map", fake_lower_program_with_source_map, raising=False)
    monkeypatch.setattr(cli, "build_universal_meta_asm", fake_build_universal_meta_asm, raising=False)
    monkeypatch.setattr(cli, "start_head_from_encoded_tape", fake_start_head_from_encoded_tape, raising=False)
    monkeypatch.setattr(cli, "RawTraceRunner", FakeRawTraceRunner, raising=False)
    monkeypatch.setattr(cli, "DebuggerSession", FakeDebuggerSession, raising=False)
    monkeypatch.setattr(cli, "DebuggerShell", FakeDebuggerShell, raising=False)

    return calls


def _run_dbg(args: list[str], monkeypatch, capsys):
    calls = _install_debugger_stubs(monkeypatch)
    exit_code = cli.main(args)
    output = capsys.readouterr().out
    return exit_code, output, calls


def test_cli_dbg_positional_fixture_uses_shell_startup_path(monkeypatch, capsys):
    exit_code, output, calls = _run_dbg(["dbg", "incrementer"], monkeypatch, capsys)

    assert exit_code == 0
    assert output.strip() == "formatted:startup:incrementer"
    assert calls["load_fixture"] == ["incrementer"]
    assert calls["build_tape"] == ["incrementer"]
    assert calls["build_universal"] == ["encoding"]
    assert calls["lower_with_source_map"] == [("START_STEP", 3)]
    assert calls["start_head"] == [True]
    assert calls["shell_inits"] == 1
    assert calls["startup_calls"] == ["incrementer"]
    assert calls["shell_cmdloop_calls"] == [None]


def test_cli_dbg_flag_and_positional_share_fixture_resolution(monkeypatch, capsys):
    positional_code, positional_output, positional_calls = _run_dbg(["dbg", "incrementer"], monkeypatch, capsys)
    flag_code, flag_output, flag_calls = _run_dbg(["dbg", "--fixture", "incrementer"], monkeypatch, capsys)

    assert positional_code == 0
    assert flag_code == 0
    assert positional_output.strip() == "formatted:startup:incrementer"
    assert flag_output.strip() == "formatted:startup:incrementer"
    assert positional_calls["load_fixture"] == ["incrementer"]
    assert flag_calls["load_fixture"] == ["incrementer"]
    assert positional_calls["runner_inits"] == flag_calls["runner_inits"]
    assert positional_calls["session_inits"] == flag_calls["session_inits"]
    assert positional_calls["startup_calls"] == ["incrementer"]
    assert flag_calls["startup_calls"] == ["incrementer"]


def test_cli_dbg_accepts_tm_and_band_artifact_paths(monkeypatch, capsys):
    calls = _install_debugger_stubs(monkeypatch)
    trace_sessions = []

    def fake_build_trace_session(tm_file, band_file, *, max_raw):
        trace_sessions.append((tm_file, band_file, max_raw))
        return SimpleNamespace(name="artifact-session")

    monkeypatch.setattr(cli, "_build_trace_session", fake_build_trace_session)

    exit_code = cli.main(["dbg", "host.tm", "input.utm.band", "--max-raw", "123"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert trace_sessions == [("host.tm", "input.utm.band", 123)]
    assert calls["load_fixture"] == []
    assert calls["shell_inits"] == 1
    assert calls["startup_calls"] == ["host.tm on input.utm.band"]
    assert output.strip() == "formatted:startup:host.tm on input.utm.band"


def test_cli_dbg_rejects_fixture_flag_with_positional_inputs(monkeypatch, capsys):
    _install_debugger_stubs(monkeypatch)

    try:
        cli.main(["dbg", "--fixture", "incrementer", "host.tm", "input.utm.band"])
    except SystemExit as exc:
        assert str(exc) == "dbg accepts either --fixture FIXTURE or positional inputs, not both"
    else:
        raise AssertionError("expected mixed fixture/artifact debugger input to fail")
