"""Teaching-facing debugger helpers layered over raw transition execution.

The package surface is split across four levels:

- ``RawTraceRunner`` provides reversible raw stepping and grouped boundaries
- ``DebuggerSession`` owns command semantics and step/back settings
- ``DebuggerRenderer`` owns deterministic plain-text formatting
- ``DebuggerShell`` exposes the fixture-mode REPL as a thin ``cmd.Cmd`` adapter
"""

from .render import (
    DebuggerActionSummary,
    DebuggerLocationSummary,
    DebuggerRenderer,
    DebuggerRunnerSummary,
    DebuggerSemanticSummary,
    DebuggerTransitionSummary,
    DebuggerViewSummary,
    format_group_step_result,
    format_source_location,
    format_trace_view,
)
from .session import ActionStatus, Boundary, DebuggerActionResult, DebuggerSession
from .shell import BACK_USAGE, HELP_TEXT, SET_USAGE, STEP_USAGE, DebuggerShell
from .trace import RawTraceGroupStepResult, RawTraceRunResult, RawTraceRunner, RawTraceSnapshot, RawTraceStepResult, RawTraceTransition, RawTraceView

__all__ = [
    "ActionStatus",
    "BACK_USAGE",
    "Boundary",
    "DebuggerActionResult",
    "DebuggerActionSummary",
    "DebuggerLocationSummary",
    "DebuggerRenderer",
    "DebuggerRunnerSummary",
    "DebuggerSemanticSummary",
    "DebuggerSession",
    "DebuggerShell",
    "DebuggerTransitionSummary",
    "DebuggerViewSummary",
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
