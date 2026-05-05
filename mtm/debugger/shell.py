"""Thin cmd.Cmd adapter for the MTM debugger session."""

from __future__ import annotations

import cmd
import textwrap

from .session import DebuggerSession

HELP_TEXT = textwrap.dedent(
    """\
    mtm debugger

    Commands:
      status               Show compact runner status
      view                 Show raw + source + semantic trace view
      where                Show current lowered source location only

      step raw             Step one raw TM transition
      step routine         Step to next lowering routine
      step instruction     Step to next Meta-ASM instruction
      step block           Step to next Meta-ASM block
      step source          Step until one simulated source-TM transition completes

      back raw             Rewind one raw TM transition
      back routine         Rewind to previous lowering routine
      back instruction     Rewind to previous Meta-ASM instruction
      back block           Rewind to previous Meta-ASM block
      back source          Rewind to previous simulated source-TM transition start

      set max-raw N        Set grouped-step raw transition guard
      help                 Show this help
      quit                 Exit debugger

    Shortcuts:
      st=status, v=view, w=where
      s=step raw, sr=step routine, si=step instruction, sb=step block, ss=step source
      b=back raw, br=back routine, bi=back instruction, bb=back block, bs=back source
      h/help/?=help, q=quit
    """
).rstrip()

STEP_USAGE = "usage: step raw|routine|instruction|block|source"
BACK_USAGE = "usage: back raw|routine|instruction|block|source"
SET_USAGE = "usage: set max-raw N"
BOUNDARIES = {"raw", "routine", "instruction", "block", "source"}


class DebuggerShell(cmd.Cmd):
    """Interactive debugger shell that delegates semantics to DebuggerSession."""

    prompt = "mtmdbg> "

    def __init__(self, session: DebuggerSession, *, stdin=None, stdout=None) -> None:
        super().__init__(stdin=stdin, stdout=stdout)
        self.session = session
        self.use_rawinput = False

    def emptyline(self) -> bool:
        return False

    def default(self, line: str) -> None:
        self._write(f"unknown command: {line}")
        self._write("type `help` for commands")

    def do_status(self, arg: str) -> None:
        self._write(self.session.status_text())

    def do_view(self, arg: str) -> None:
        self._write(self.session.view_text())

    def do_where(self, arg: str) -> None:
        self._write(self.session.where_text())

    def do_step(self, arg: str) -> None:
        boundary = self._parse_boundary(arg, usage=STEP_USAGE)
        if boundary is None:
            return
        self._write(self.session.step_text(boundary))

    def do_back(self, arg: str) -> None:
        boundary = self._parse_boundary(arg, usage=BACK_USAGE)
        if boundary is None:
            return
        self._write(self.session.back_text(boundary))

    def do_set(self, arg: str) -> None:
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
        self._write(self.session.set_max_raw(value))

    def do_help(self, arg: str) -> None:
        self._write(HELP_TEXT)

    def do_h(self, arg: str) -> None:
        self.do_help(arg)

    def do_quit(self, arg: str) -> bool:
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
        self.do_step("raw")

    def do_sr(self, arg: str) -> None:
        self.do_step("routine")

    def do_si(self, arg: str) -> None:
        self.do_step("instruction")

    def do_sb(self, arg: str) -> None:
        self.do_step("block")

    def do_ss(self, arg: str) -> None:
        self.do_step("source")

    def do_b(self, arg: str) -> None:
        self.do_back("raw")

    def do_br(self, arg: str) -> None:
        self.do_back("routine")

    def do_bi(self, arg: str) -> None:
        self.do_back("instruction")

    def do_bb(self, arg: str) -> None:
        self.do_back("block")

    def do_bs(self, arg: str) -> None:
        self.do_back("source")

    def do_EOF(self, arg: str) -> bool:
        return True

    def _parse_boundary(self, arg: str, *, usage: str) -> str | None:
        boundary = arg.strip()
        if not boundary:
            self._write(usage)
            return None
        if boundary not in BOUNDARIES:
            self._write(f"unknown boundary: {boundary}")
            self._write(usage)
            return None
        return boundary

    def _write(self, text: str) -> None:
        self.stdout.write(text)
        self.stdout.write("\n")


__all__ = ["BACK_USAGE", "DebuggerShell", "HELP_TEXT", "SET_USAGE", "STEP_USAGE"]
