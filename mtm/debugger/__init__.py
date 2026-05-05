"""Teaching-facing debugger helpers layered over raw transition execution.

The package surface is intentionally small:

- ``RawTraceRunner`` provides reversible raw stepping
- source maps connect raw rows back to lowered instructions
- grouped stepping moves by routine, instruction, block, or UTM source step
- renderers format the current raw and semantic view for text output
"""

from .render import format_group_step_result, format_source_location, format_trace_view
from .session import ActionStatus, Boundary, DebuggerActionResult, DebuggerSession
from .trace import RawTraceGroupStepResult, RawTraceRunResult, RawTraceRunner, RawTraceSnapshot, RawTraceStepResult, RawTraceTransition, RawTraceView

__all__ = [
    "ActionStatus",
    "Boundary",
    "DebuggerActionResult",
    "DebuggerSession",
    "RawTraceGroupStepResult",
    "RawTraceRunResult",
    "RawTraceRunner",
    "RawTraceSnapshot",
    "RawTraceStepResult",
    "RawTraceTransition",
    "RawTraceView",
    "format_group_step_result",
    "format_source_location",
    "format_trace_view",
]
