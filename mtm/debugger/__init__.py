"""Teaching-facing debugger helpers layered over raw transition execution.

The package surface is split across three levels:

- ``RawTraceRunner`` provides reversible raw stepping and grouped boundaries
- ``DebuggerSession`` formats status, where/view output, and step/back actions
- ``DebuggerShell`` exposes the fixture-mode REPL as a thin ``cmd.Cmd`` adapter
"""

from .render import format_group_step_result, format_source_location, format_trace_view
from .session import ActionStatus, Boundary, DebuggerActionResult, DebuggerSession
from .shell import BACK_USAGE, HELP_TEXT, SET_USAGE, STEP_USAGE, DebuggerShell
from .trace import RawTraceGroupStepResult, RawTraceRunResult, RawTraceRunner, RawTraceSnapshot, RawTraceStepResult, RawTraceTransition, RawTraceView

__all__ = [
    "ActionStatus",
    "BACK_USAGE",
    "Boundary",
    "DebuggerActionResult",
    "DebuggerSession",
    "DebuggerShell",
    "HELP_TEXT",
    "RawTraceGroupStepResult",
    "RawTraceRunResult",
    "RawTraceRunner",
    "RawTraceSnapshot",
    "RawTraceStepResult",
    "RawTraceTransition",
    "RawTraceView",
    "SET_USAGE",
    "STEP_USAGE",
    "format_group_step_result",
    "format_source_location",
    "format_trace_view",
]
