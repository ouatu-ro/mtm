from __future__ import annotations

from contextlib import redirect_stdout
import io

from mtm.debugger.shell import DebuggerShell
from mtm.debugger.render_rich import RichRenderer
from mtm.debugger.render_text import PlainTextRenderer


def _run_command(shell: DebuggerShell, command: str) -> tuple[str, object | None]:
    buffer = io.StringIO()
    old_stdout = getattr(shell, "stdout", None)
    try:
        shell.stdout = buffer
        with redirect_stdout(buffer):
            result = shell.onecmd(command)
    finally:
        shell.stdout = old_stdout
    return buffer.getvalue().strip(), result


def _assert_exact_lines(output: str, *lines: str) -> None:
    assert output.splitlines() == list(lines)


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def status(self):
        self.calls.append(("status", None))
        return {"kind": "status", "payload": "status-payload"}

    def where(self):
        self.calls.append(("where", None))
        return {"kind": "where", "payload": "where-payload"}

    def view(self):
        self.calls.append(("view", None))
        return {"kind": "view", "payload": "view-payload"}

    def step_many(self, boundary: str, count: int):
        self.calls.append(("step_many", (boundary, count)))
        return {"kind": "action", "payload": f"step-payload-{boundary}-{count}"}

    def back_many(self, boundary: str, count: int):
        self.calls.append(("back_many", (boundary, count)))
        return {"kind": "action", "payload": f"back-payload-{boundary}-{count}"}

    def set_max_raw(self, value: int) -> int:
        self.calls.append(("set_max_raw", value))
        return value


class FakePresenter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def startup_doc(self, *, fixture_name: str, status):
        self.calls.append(("startup_doc", (fixture_name, status)))
        return {"doc": f"startup:{fixture_name}:{status['payload']}"}

    def status_doc(self, payload):
        self.calls.append(("status_doc", payload))
        return {"doc": f"status:{payload['payload']}"}

    def where_doc(self, payload):
        self.calls.append(("where_doc", payload))
        return {"doc": f"where:{payload['payload']}"}

    def view_doc(self, payload):
        self.calls.append(("view_doc", payload))
        return {"doc": f"view:{payload['payload']}"}

    def action_doc(self, payload):
        self.calls.append(("action_doc", payload))
        return {"doc": f"action:{payload['payload']}"}

    def help_doc(self, topic=None):
        self.calls.append(("help_doc", topic))
        if topic == "nope":
            return None
        return {"doc": f"help:{topic or '<root>'}"}


class FakeRenderer:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def render(self, document) -> str:
        self.calls.append(document)
        return f"rendered:{document['doc']}"


def _shell_with_fakes() -> tuple[FakeSession, FakePresenter, FakeRenderer, DebuggerShell]:
    session = FakeSession()
    presenter = FakePresenter()
    renderer = FakeRenderer()
    shell = DebuggerShell(session, presenter=presenter, renderer=renderer)
    return session, presenter, renderer, shell


def test_debugger_shell_status_where_view_use_session_presenter_renderer_wiring() -> None:
    _, presenter, renderer, shell = _shell_with_fakes()

    output, _ = _run_command(shell, "status")
    assert output == "rendered:status:status-payload"
    assert presenter.calls[-1][0] == "status_doc"
    assert renderer.calls[-1] == {"doc": "status:status-payload"}

    output, _ = _run_command(shell, "where")
    assert output == "rendered:where:where-payload"
    assert presenter.calls[-1][0] == "where_doc"

    output, _ = _run_command(shell, "view")
    assert output == "rendered:view:view-payload"
    assert presenter.calls[-1][0] == "view_doc"


def test_debugger_shell_step_aliases_parse_boundaries() -> None:
    session, presenter, renderer, shell = _shell_with_fakes()
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
        assert ("step_many", (boundary, 1)) in session.calls
        assert output == f"rendered:action:step-payload-{boundary}-1"
        assert presenter.calls[-1][0] == "action_doc"
        assert renderer.calls[-1] == {"doc": f"action:step-payload-{boundary}-1"}


def test_debugger_shell_step_repeat_counts() -> None:
    session, _, _, shell = _shell_with_fakes()
    for command, boundary, count in (
        ("step raw 10", "raw", 10),
        ("s 10", "raw", 10),
        ("si 3", "instruction", 3),
        ("step block 2", "block", 2),
    ):
        session.calls.clear()
        output, _ = _run_command(shell, command)
        assert ("step_many", (boundary, count)) in session.calls
        assert output == f"rendered:action:step-payload-{boundary}-{count}"


def test_debugger_shell_back_aliases_parse_boundaries() -> None:
    session, _, _, shell = _shell_with_fakes()
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
        assert ("back_many", (boundary, 1)) in session.calls
        assert output == f"rendered:action:back-payload-{boundary}-1"


def test_debugger_shell_back_repeat_counts() -> None:
    session, _, _, shell = _shell_with_fakes()
    for command, boundary, count in (
        ("back raw 10", "raw", 10),
        ("b 10", "raw", 10),
        ("bi 3", "instruction", 3),
        ("back block 2", "block", 2),
    ):
        session.calls.clear()
        output, _ = _run_command(shell, command)
        assert ("back_many", (boundary, count)) in session.calls
        assert output == f"rendered:action:back-payload-{boundary}-{count}"


def test_debugger_shell_boundary_parsing_errors() -> None:
    _, _, _, shell = _shell_with_fakes()
    output, _ = _run_command(shell, "step")
    _assert_exact_lines(output, "usage: step raw|routine|instruction|block|source [N]")

    output, _ = _run_command(shell, "step invalid")
    _assert_exact_lines(output, "unknown boundary: invalid", "usage: step raw|routine|instruction|block|source [N]")

    output, _ = _run_command(shell, "back")
    _assert_exact_lines(output, "usage: back raw|routine|instruction|block|source [N]")

    output, _ = _run_command(shell, "back invalid")
    _assert_exact_lines(output, "unknown boundary: invalid", "usage: back raw|routine|instruction|block|source [N]")

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
    session, _, _, shell = _shell_with_fakes()

    output, _ = _run_command(shell, "set max-raw 17")
    assert output == "max_raw=17"
    assert ("set_max_raw", 17) in session.calls

    output, _ = _run_command(shell, "set")
    _assert_exact_lines(output, "usage: set max-raw N")

    output, _ = _run_command(shell, "set max-raw")
    _assert_exact_lines(output, "usage: set max-raw N")

    for command in ("set max-raw abc", "set max-raw 0"):
        output, _ = _run_command(shell, command)
        _assert_exact_lines(output, "max-raw must be a positive integer", "usage: set max-raw N")

    output, _ = _run_command(shell, "set unknown 10")
    _assert_exact_lines(output, "unknown setting: unknown", "usage: set max-raw N")


def test_debugger_shell_help_uses_presenter_wiring_and_aliases() -> None:
    _, presenter, _, shell = _shell_with_fakes()

    output, _ = _run_command(shell, "help")
    assert output == "rendered:help:<root>"
    assert presenter.calls[-1] == ("help_doc", None)

    output, _ = _run_command(shell, "help step raw")
    assert output == "rendered:help:step raw"
    assert presenter.calls[-1] == ("help_doc", "step raw")

    output, _ = _run_command(shell, "h")
    assert output == "rendered:help:<root>"

    output, _ = _run_command(shell, "?")
    assert output == "rendered:help:<root>"

    output, _ = _run_command(shell, "help nope")
    _assert_exact_lines(output, "unknown help topic: nope", "type `help` for commands")


def test_debugger_shell_render_startup_uses_same_presenter_renderer_stack() -> None:
    session, presenter, renderer, shell = _shell_with_fakes()

    startup = shell.render_startup("incrementer")

    assert startup == "rendered:startup:incrementer:status-payload"
    assert ("status", None) in session.calls
    assert presenter.calls[-1][0] == "startup_doc"
    assert renderer.calls[-1] == {"doc": "startup:incrementer:status-payload"}


def test_debugger_shell_defaults_to_plain_text_without_tty() -> None:
    shell = DebuggerShell(FakeSession(), stdout=io.StringIO())

    assert isinstance(shell.renderer, PlainTextRenderer)


def test_debugger_shell_defaults_to_rich_with_tty_stdout(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)

    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    shell = DebuggerShell(FakeSession(), stdout=FakeTTY())

    assert isinstance(shell.renderer, RichRenderer)
