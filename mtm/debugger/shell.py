"""Thin ``cmd.Cmd`` adapter for the debugger session, presenter, and renderer.

This module is the command-line surface of the debugger. It keeps parsing and
output formatting in one place while delegating execution to the session and
document rendering to the presenter/renderers.
"""

from __future__ import annotations

import cmd
import os
import sys

from .presenter import DebuggerPresenter
from .render_rich import RichRenderer
from .render_text import PlainTextRenderer
from .session import DebuggerSession

STEP_USAGE = "usage: step raw|routine|instruction|block|source [N]"
BACK_USAGE = "usage: back raw|routine|instruction|block|source [N]"
SET_USAGE = "usage: set max-raw N"
COUNT_ERROR = "count must be a positive integer"
BOUNDARIES = {"raw", "routine", "instruction", "block", "source"}


class DebuggerShell(cmd.Cmd):
    """Interactive debugger shell for stepping through traced TM execution.

    The shell handles command parsing, aliases, and output routing. It does
    not own the debugger logic itself; that stays in the session and presenter
    layers so the interactive surface remains thin and testable.
    """

    prompt = "mtmdbg> "

    def __init__(
        self,
        session: DebuggerSession,
        *,
        stdin=None,
        stdout=None,
        presenter: DebuggerPresenter | None = None,
        renderer: PlainTextRenderer | None = None,
    ) -> None:
        """Build a shell around an existing session and optional presentation stack."""

        super().__init__(stdin=stdin, stdout=stdout)
        self.session = session
        self.presenter = DebuggerPresenter() if presenter is None else presenter
        self.renderer = self._default_renderer(stdout) if renderer is None else renderer
        self.use_rawinput = stdin is None and stdout is None

    def emptyline(self) -> bool:
        """Ignore blank lines instead of repeating the previous command."""

        return False

    def default(self, line: str) -> None:
        """Handle unknown commands and ``?`` help shortcuts."""

        if line == "?":
            self.do_help("")
            return
        if line.startswith("? "):
            self.do_help(line[2:])
            return
        self._write(f"unknown command: {line}")
        self._write("type `help` for commands")

    def render_startup(self, fixture_name: str) -> str:
        """Render the startup banner for a named debugger fixture."""

        return self.renderer.render(self.presenter.startup_doc(fixture_name=fixture_name, status=self.session.status()))

    def do_status(self, arg: str) -> None:
        """Print the current debugger status."""

        self._write_doc(self.presenter.status_doc(self.session.status()))

    def do_view(self, arg: str) -> None:
        """Print the current debugger view."""

        self._write_doc(self.presenter.view_doc(self.session.view()))

    def do_where(self, arg: str) -> None:
        """Print the current source-location explanation."""

        self._write_doc(self.presenter.where_doc(self.session.where()))

    def do_step(self, arg: str) -> None:
        """Step forward across a boundary and print the resulting action."""

        parsed = self._parse_boundary_and_count(arg, usage=STEP_USAGE)
        if parsed is None:
            return
        boundary, count = parsed
        self._write_doc(self.presenter.action_doc(self.session.step_many(boundary, count)))

    def do_back(self, arg: str) -> None:
        """Step backward across a boundary and print the resulting action."""

        parsed = self._parse_boundary_and_count(arg, usage=BACK_USAGE)
        if parsed is None:
            return
        boundary, count = parsed
        self._write_doc(self.presenter.action_doc(self.session.back_many(boundary, count)))

    def do_set(self, arg: str) -> None:
        """Update debugger settings from the command line."""

        parts = arg.split()
        if len(parts) != 2:
            self._write(SET_USAGE)
            return
        setting, raw_value = parts
        if setting != "max-raw":
            self._write(f"unknown setting: {setting}")
            self._write(SET_USAGE)
            return
        try:
            value = int(raw_value)
        except ValueError:
            self._write("max-raw must be a positive integer")
            self._write(SET_USAGE)
            return
        if value <= 0:
            self._write("max-raw must be a positive integer")
            self._write(SET_USAGE)
            return
        self._write(f"max_raw={self.session.set_max_raw(value)}")

    def do_help(self, arg: str) -> None:
        """Print general help or a specific help topic."""

        topic = " ".join(arg.split())
        document = self.presenter.help_doc(topic or None)
        if document is None:
            self._write(f"unknown help topic: {topic}")
            self._write("type `help` for commands")
            return
        self._write_doc(document)

    def do_h(self, arg: str) -> None:
        self.do_help(arg)

    def do_quit(self, arg: str) -> bool:
        """Exit the debugger shell."""

        return True

    def do_q(self, arg: str) -> bool:
        return self.do_quit(arg)

    def do_st(self, arg: str) -> None:
        self.do_status(arg)

    def do_v(self, arg: str) -> None:
        self.do_view(arg)

    def do_w(self, arg: str) -> None:
        self.do_where(arg)

    def do_s(self, arg: str) -> None:
        self.do_step(self._alias_arg("raw", arg))

    def do_sr(self, arg: str) -> None:
        self.do_step(self._alias_arg("routine", arg))

    def do_si(self, arg: str) -> None:
        self.do_step(self._alias_arg("instruction", arg))

    def do_sb(self, arg: str) -> None:
        self.do_step(self._alias_arg("block", arg))

    def do_ss(self, arg: str) -> None:
        self.do_step(self._alias_arg("source", arg))

    def do_b(self, arg: str) -> None:
        self.do_back(self._alias_arg("raw", arg))

    def do_br(self, arg: str) -> None:
        self.do_back(self._alias_arg("routine", arg))

    def do_bi(self, arg: str) -> None:
        self.do_back(self._alias_arg("instruction", arg))

    def do_bb(self, arg: str) -> None:
        self.do_back(self._alias_arg("block", arg))

    def do_bs(self, arg: str) -> None:
        self.do_back(self._alias_arg("source", arg))

    def do_EOF(self, arg: str) -> bool:
        """Exit when the input stream ends."""

        return True

    def format_output(self, text: str) -> str:
        """Allow subclasses to post-process rendered output."""

        return text

    def _default_renderer(self, stdout):
        target = stdout if stdout is not None else sys.stdout
        is_tty = getattr(target, "isatty", lambda: False)()
        color_enabled = is_tty and "NO_COLOR" not in os.environ
        return RichRenderer(color=True) if color_enabled else PlainTextRenderer()

    def _parse_boundary_and_count(self, arg: str, *, usage: str) -> tuple[str, int] | None:
        parts = arg.split()
        if not parts:
            self._write(usage)
            return None
        if len(parts) > 2:
            self._write(usage)
            return None
        boundary = parts[0]
        if boundary not in BOUNDARIES:
            self._write(f"unknown boundary: {boundary}")
            self._write(usage)
            return None
        count = 1
        if len(parts) == 2:
            try:
                count = int(parts[1])
            except ValueError:
                self._write(COUNT_ERROR)
                self._write(usage)
                return None
            if count <= 0:
                self._write(COUNT_ERROR)
                self._write(usage)
                return None
        return boundary, count

    @staticmethod
    def _alias_arg(boundary: str, arg: str) -> str:
        stripped = arg.strip()
        return boundary if not stripped else f"{boundary} {stripped}"

    def _write_doc(self, document) -> None:
        self._write(self.renderer.render(document))

    def _write(self, text: str) -> None:
        self.stdout.write(text)
        self.stdout.write("\n")


HELP_TEXT = PlainTextRenderer().render(DebuggerPresenter().help_doc(None))


__all__ = ["BACK_USAGE", "DebuggerShell", "HELP_TEXT", "SET_USAGE", "STEP_USAGE"]
