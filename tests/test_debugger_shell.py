from __future__ import annotations

from contextlib import redirect_stdout
import io
import importlib
from typing import Any

try:
    from mtm.debugger import DebuggerShell
except ImportError:
    DebuggerShell = importlib.import_module("mtm.debugger.shell").DebuggerShell
DebuggerRenderer = importlib.import_module("mtm.debugger.render").DebuggerRenderer


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

    def step_many_text(self, boundary: str, count: int) -> str:
        self._record("step_many_text", (boundary, count))
        return f"step {boundary} x{count}-text"

    def step(self, boundary: str) -> str:
        return self.step_text(boundary)

    def back_text(self, boundary: str) -> str:
        self._record("back_text", boundary)
        return f"back {boundary}-text"

    def back_many_text(self, boundary: str, count: int) -> str:
        self._record("back_many_text", (boundary, count))
        return f"back {boundary} x{count}-text"

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
        assert ("step_many_text", (boundary, 1)) in session.calls
        assert output == f"step {boundary} x1-text"


def test_debugger_shell_step_aliases_accept_repeat_counts() -> None:
    session, shell = _shell_with_session()
    for command, payload in (
        ("step raw 10", ("raw", 10)),
        ("s 10", ("raw", 10)),
        ("si 3", ("instruction", 3)),
        ("step block 2", ("block", 2)),
    ):
        session.calls.clear()
        output, _ = _run_command(shell, command)
        assert ("step_many_text", payload) in session.calls
        assert output == f"step {payload[0]} x{payload[1]}-text"


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
        assert ("back_many_text", (boundary, 1)) in session.calls
        assert output == f"back {boundary} x1-text"


def test_debugger_shell_back_aliases_accept_repeat_counts() -> None:
    session, shell = _shell_with_session()
    for command, payload in (
        ("back raw 10", ("raw", 10)),
        ("b 10", ("raw", 10)),
        ("bi 3", ("instruction", 3)),
        ("back block 2", ("block", 2)),
    ):
        session.calls.clear()
        output, _ = _run_command(shell, command)
        assert ("back_many_text", payload) in session.calls
        assert output == f"back {payload[0]} x{payload[1]}-text"


def test_debugger_shell_boundary_parsing_errors() -> None:
    _, shell = _shell_with_session()
    output, _ = _run_command(shell, "step")
    _assert_exact_lines(output, "usage: step raw|routine|instruction|block|source [N]")

    output, _ = _run_command(shell, "step invalid")
    _assert_exact_lines(
        output,
        "unknown boundary: invalid",
        "usage: step raw|routine|instruction|block|source [N]",
    )

    output, _ = _run_command(shell, "back")
    _assert_exact_lines(output, "usage: back raw|routine|instruction|block|source [N]")

    output, _ = _run_command(shell, "back invalid")
    _assert_exact_lines(
        output,
        "unknown boundary: invalid",
        "usage: back raw|routine|instruction|block|source [N]",
    )

    for command, usage in (
        ("step raw 0", "usage: step raw|routine|instruction|block|source [N]"),
        ("step raw nope", "usage: step raw|routine|instruction|block|source [N]"),
        ("back instruction 0", "usage: back raw|routine|instruction|block|source [N]"),
        ("back instruction nope", "usage: back raw|routine|instruction|block|source [N]"),
    ):
        output, _ = _run_command(shell, command)
        _assert_exact_lines(output, "count must be a positive integer", usage)

    output, _ = _run_command(shell, "step raw 1 2")
    _assert_exact_lines(output, "usage: step raw|routine|instruction|block|source [N]")


def test_debugger_shell_set_command_validation() -> None:
    session, shell = _shell_with_session()
    output, _ = _run_command(shell, "set max-raw 17")
    assert output == "max_raw: 17" or output == "max_raw=17"
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
    assert "MTM debugger" in help_output
    assert "Command" in help_output
    assert "Alias" in help_output
    assert "Meaning" in help_output
    assert "status" in help_output and "Show compact runner status" in help_output
    assert "view" in help_output and "Show raw + source + semantic trace view" in help_output
    assert "step raw [N]" in help_output and "Step one or N raw TM transitions" in help_output
    assert "back source [N]" in help_output and "Rewind to the previous N simulated source-TM transitions" in help_output
    assert "set max-raw N" in help_output and "Set grouped-step raw transition guard" in help_output
    assert "Visual Legend:" in help_output
    assert "RAW          raw=<step>" in help_output
    assert "INSTRUCTION  OPCODE <ARGS>" in help_output
    assert "NEXT ROW     state=<row state>" in help_output
    assert "st" in help_output
    assert "s" in help_output
    assert "q" in help_output

    help_short, _ = _run_command(shell, "?")
    help_alias, _ = _run_command(shell, "h")
    assert help_short == help_alias == help_output


def test_debugger_shell_help_topics_and_aliases() -> None:
    _, shell = _shell_with_session()

    output, _ = _run_command(shell, "help step raw")
    assert "step raw" in output
    assert "alias: s" in output
    assert "Advance by exactly one raw TM transition." in output
    assert "You can pass N, as in `s 10` or `step raw 10`, to repeat the command." in output
    assert "Output:" in output
    assert "RAW          raw=<step>  head=<raw tape head>  read='<symbol>'  state=<raw TM state>" in output
    assert "INSTRUCTION  OPCODE <ARGS>" in output
    assert "NEXT ROW     state=<row state>  read='<symbol>'  write='<symbol>'  move=<L|R|S>  next=<next raw state>" in output
    assert "Fields:" in output
    assert "  move    = Raw TM head movement: L, R, or S" in output

    alias_output, _ = _run_command(shell, "help s")
    assert alias_output == output

    output, _ = _run_command(shell, "help step")
    assert "step <boundary> [N]" in output
    assert "Boundaries: raw, routine, instruction, block, source" in output
    assert "Optional N repeats that boundary step N times" in output

    output, _ = _run_command(shell, "help set")
    assert "set max-raw N" in output
    assert "Grouped commands like `step instruction` stop with status `max_raw`" in output

    output, _ = _run_command(shell, "help status")
    assert "status" in output
    assert "Output:" in output
    assert "SOURCE       block=<block>  instr=<instruction index>  routine=<lowering routine>  op=<sub-step>" in output

    output, _ = _run_command(shell, "help where")
    assert "where" in output
    assert "NEXT ROW     state=<row state>" in output

    output, _ = _run_command(shell, "help nope")
    _assert_exact_lines(
        output,
        "unknown help topic: nope",
        "type `help` for commands",
    )


def test_debugger_shell_unknown_command() -> None:
    _, shell = _shell_with_session()
    output, _ = _run_command(shell, "does-not-exist")
    _assert_exact_lines(
        output,
        "unknown command: does-not-exist",
        "type `help` for commands",
    )


def test_debugger_renderer_colorizes_status_when_enabled() -> None:
    renderer = DebuggerRenderer(color=True)
    styled = renderer.format_output("running  raw=0  max_raw=100000  hist=0/0")
    assert "\x1b[" in styled
    assert "\x1b[1;37m" not in styled
    assert "\x1b[2;37m" not in styled


def test_debugger_renderer_does_not_clobber_help_rows() -> None:
    renderer = DebuggerRenderer(color=True)
    styled = renderer.format_output(DebuggerRenderer(color=False).render_help())
    assert "step raw [N]" in styled and "| s" in styled and "Step one or N raw TM transitions" in styled
    assert "step block [N]" in styled and "| sb" in styled and "Step to the next N Meta-ASM blocks" in styled
    assert "back source [N]" in styled and "| bs" in styled and "previous N simulated source-TM transitions" in styled
    assert "RAW" in styled and "<step>" in styled and "<raw TM state>" in styled
    assert "OPCODE" in styled and "<ARGS>" in styled


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
