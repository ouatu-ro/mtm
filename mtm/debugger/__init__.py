"""Debugger surfaces layered over reversible raw transition execution."""

from .facts import TraceFacts
from .help import COMMAND_SPECS, FIELD_DOCS
from .presenter import DebuggerPresenter
from .queries import ActionRow, DebuggerQueries, SnapshotRow, SourceRow, StatusRow, TransitionRow, ViewRow, WhereRow
from .render_text import PlainTextRenderer
from .session import ActionStatus, Boundary, DebuggerActionResult, DebuggerSession
from .shell import BACK_USAGE, HELP_TEXT, SET_USAGE, STEP_USAGE, DebuggerShell
from .trace import RawTraceGroupStepResult, RawTraceRunResult, RawTraceRunner, RawTraceSnapshot, RawTraceStepResult, RawTraceTransition, RawTraceView
from .trace_text import format_group_step_result, format_source_location, format_trace_view

__all__ = [
    "ActionRow",
    "ActionStatus",
    "BACK_USAGE",
    "Boundary",
    "COMMAND_SPECS",
    "DebuggerActionResult",
    "DebuggerPresenter",
    "DebuggerQueries",
    "DebuggerSession",
    "DebuggerShell",
    "FIELD_DOCS",
    "HELP_TEXT",
    "PlainTextRenderer",
    "RawTraceGroupStepResult",
    "RawTraceRunResult",
    "RawTraceRunner",
    "RawTraceSnapshot",
    "RawTraceStepResult",
    "RawTraceTransition",
    "RawTraceView",
    "SET_USAGE",
    "STEP_USAGE",
    "SnapshotRow",
    "SourceRow",
    "StatusRow",
    "TraceFacts",
    "TransitionRow",
    "ViewRow",
    "WhereRow",
    "format_group_step_result",
    "format_source_location",
    "format_trace_view",
]
