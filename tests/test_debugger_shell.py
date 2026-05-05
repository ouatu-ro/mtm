from __future__ import annotations

from contextlib import redirect_stdout
import io
import importlib
from typing import Any

try:
    from mtm.debugger import DebuggerShell
except ImportError:
    DebuggerShell = importlib.import_module("mtm.debugger.shell").DebuggerShell


def _build_shell(session: object) -> object:
    last_error: Exception | None = None
    for factory in (
        lambda: DebuggerShell(session),
        lambda: DebuggerShell(runner_session=session),
        lambda: DebuggerShell(debugger_session=session),
        lambda: DebuggerShell(session=session),
        lambda: DebuggerShell(),
    ):
        try:
            return factory()
        except TypeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise TypeError("unreachable")


def _attach_session(shell: object, session: object) -> None:
    for attr in ("session", "debugger_session", "runner_session"):
        if hasattr(shell, attr):
            setattr(shell, attr, session)
            return
    # Fallback for implementations that set session dynamically.
    setattr(shell, "session", session)


def _run_command(shell: object, command: str) -> tuple[str, object | None]:
    buffer = io.StringIO()
    old_stdout = getattr(shell, "stdout", None)
    try:
        shell.stdout = buffer
        with redirect_stdout(buffer):
            result = shell.onecmd(command)
    finally:
        shell.stdout = old_stdout

    output = buffer.getvalue().strip()
    if isinstance(result, str) and not output:
        output = result
    return output, result


def _assert_exact_lines(output: str, *lines: str) -> None:
    assert output.splitlines() == list(lines)


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def _record(self, kind: str, value: Any) -> None:
        self.calls.append((kind, value))

    def status_text(self) -> str:
        self._record("status_text", None)
        return "status-text"

    def status(self) -> str:
        return self.status_text()

    def where_text(self) -> str:
        self._record("where_text", None)
        return "where-text"

    def where(self) -> str:
        return self.where_text()

    def view_text(self) -> str:
        self._record("view_text", None)
        return "view-text"

    def view(self) -> str:
        return self.view_text()

    def step_text(self, boundary: str) -> str:
        self._record("step_text", boundary)
        return f"step {boundary}-text"

    def step(self, boundary: str) -> str:
        return self.step_text(boundary)

    def back_text(self, boundary: str) -> str:
        self._record("back_text", boundary)
        return f"back {boundary}-text"

    def back(self, boundary: str) -> str:
        return self.back_text(boundary)

    def set_max_raw(self, value: int) -> str:
        self._record("set_max_raw", value)
        return f"max_raw: {value}"


def _shell_with_session() -> tuple[FakeSession, object]:
    session = FakeSession()
    shell = _build_shell(session)
    _attach_session(shell, session)
    return session, shell


def test_debugger_shell_status_view_where_shortcuts() -> None:
    session, shell = _shell_with_session()
    status_output, _ = _run_command(shell, "status")
    status_alias_output, _ = _run_command(shell, "st")
    assert status_output == "status-text"
    assert status_alias_output == status_output
    assert ("status_text", None) in session.calls

    where_output, _ = _run_command(shell, "where")
    where_alias_output, _ = _run_command(shell, "w")
    assert where_output == "where-text"
    assert where_alias_output == where_output
    assert ("where_text", None) in session.calls

    view_output, _ = _run_command(shell, "view")
    view_alias_output, _ = _run_command(shell, "v")
    assert view_output == "view-text"
    assert view_alias_output == view_output
    assert ("view_text", None) in session.calls


def test_debugger_shell_step_aliases_parse_boundaries() -> None:
    session, shell = _shell_with_session()
    for command, boundary in (
        ("step raw", "raw"),
        ("s", "raw"),
        ("step routine", "routine"),
        ("sr", "routine"),
        ("step instruction", "instruction"),
        ("si", "instruction"),
        ("step block", "block"),
        ("sb", "block"),
        ("step source", "source"),
        ("ss", "source"),
    ):
        session.calls.clear()
        output, _ = _run_command(shell, command)
        assert ("step_text", boundary) in session.calls
        assert output == f"step {boundary}-text"


def test_debugger_shell_back_aliases_parse_boundaries() -> None:
    session, shell = _shell_with_session()
    for command, boundary in (
        ("back raw", "raw"),
        ("b", "raw"),
        ("back routine", "routine"),
        ("br", "routine"),
        ("back instruction", "instruction"),
        ("bi", "instruction"),
        ("back block", "block"),
        ("bb", "block"),
        ("back source", "source"),
        ("bs", "source"),
    ):
        session.calls.clear()
        output, _ = _run_command(shell, command)
        assert ("back_text", boundary) in session.calls
        assert output == f"back {boundary}-text"


def test_debugger_shell_boundary_parsing_errors() -> None:
    _, shell = _shell_with_session()
    output, _ = _run_command(shell, "step")
    _assert_exact_lines(output, "usage: step raw|routine|instruction|block|source")

    output, _ = _run_command(shell, "step invalid")
    _assert_exact_lines(
        output,
        "unknown boundary: invalid",
        "usage: step raw|routine|instruction|block|source",
    )

    output, _ = _run_command(shell, "back")
    _assert_exact_lines(output, "usage: back raw|routine|instruction|block|source")

    output, _ = _run_command(shell, "back invalid")
    _assert_exact_lines(
        output,
        "unknown boundary: invalid",
        "usage: back raw|routine|instruction|block|source",
    )


def test_debugger_shell_set_command_validation() -> None:
    session, shell = _shell_with_session()
    output, _ = _run_command(shell, "set max-raw 17")
    assert output == "max_raw: 17"
    assert ("set_max_raw", 17) in session.calls

    output, _ = _run_command(shell, "set")
    _assert_exact_lines(output, "usage: set max-raw N")

    output, _ = _run_command(shell, "set max-raw")
    _assert_exact_lines(output, "usage: set max-raw N")

    for command in ("set max-raw abc", "set max-raw 0"):
        output, _ = _run_command(shell, command)
        _assert_exact_lines(
            output,
            "max-raw must be a positive integer",
            "usage: set max-raw N",
        )

    output, _ = _run_command(shell, "set unknown 10")
    _assert_exact_lines(
        output,
        "unknown setting: unknown",
        "usage: set max-raw N",
    )


def test_debugger_shell_help_and_aliases() -> None:
    _, shell = _shell_with_session()
    help_output, _ = _run_command(shell, "help")
    assert "mtm debugger" in help_output
    assert "  status               Show compact runner status" in help_output
    assert "  view                 Show raw + source + semantic trace view" in help_output
    assert "  where                Show current lowered source location only" in help_output
    assert "  step raw             Step one raw TM transition" in help_output
    assert "  step routine         Step to next lowering routine" in help_output
    assert "  step instruction     Step to next Meta-ASM instruction" in help_output
    assert "  step block           Step to next Meta-ASM block" in help_output
    assert "  step source          Step until one simulated source-TM transition completes" in help_output
    assert "  back raw             Rewind one raw TM transition" in help_output
    assert "  back routine         Rewind to previous lowering routine" in help_output
    assert "  back instruction     Rewind to previous Meta-ASM instruction" in help_output
    assert "  back block           Rewind to previous Meta-ASM block" in help_output
    assert "  back source          Rewind to previous simulated source-TM transition start" in help_output
    assert "  set max-raw N        Set grouped-step raw transition guard" in help_output
    assert "  help                 Show this help" in help_output
    assert "  quit                 Exit debugger" in help_output
    assert "  st=status, v=view, w=where" in help_output
    assert "  s=step raw, sr=step routine, si=step instruction, sb=step block, ss=step source" in help_output
    assert "  b=back raw, br=back routine, bi=back instruction, bb=back block, bs=back source" in help_output
    assert "  h/help/?=help, q=quit" in help_output

    help_short, _ = _run_command(shell, "?")
    help_alias, _ = _run_command(shell, "h")
    assert help_short == help_alias == help_output


def test_debugger_shell_unknown_command() -> None:
    _, shell = _shell_with_session()
    output, _ = _run_command(shell, "does-not-exist")
    _assert_exact_lines(
        output,
        "unknown command: does-not-exist",
        "type `help` for commands",
    )


def _assert_quit_stops(shell: object) -> None:
    try:
        _, stopped = _run_command(shell, "quit")
    except SystemExit as exc:
        assert exc.code in (None, 0)
        return
    assert stopped is True or stopped is None


def test_debugger_shell_quit_aliases() -> None:
    _, shell = _shell_with_session()
    _assert_quit_stops(shell)

    _, shell = _shell_with_session()
    try:
        _, stopped = _run_command(shell, "q")
    except SystemExit as exc:
        assert exc.code in (None, 0)
        return
    assert stopped is True or stopped is None
