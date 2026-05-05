"""Shared debugger presentation model.

These dataclasses are the neutral document format that the debugger presenter
emits. They intentionally describe layout-independent content so the same
document can be rendered in text, tests, or other front ends.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ROLE_STATUS = "status"
ROLE_RAW = "raw"
ROLE_SOURCE = "source"
ROLE_INSTRUCTION = "instruction"
ROLE_TRANSITION = "transition"
ROLE_TAPE = "tape"
ROLE_SEMANTIC = "semantic"
ROLE_HELP = "help"
ROLE_WARNING = "warning"


@dataclass(frozen=True)
class Field:
    """One named value inside a record-style presentation block."""
    key: str
    value: Any
    role: str | None = None
    doc: str | None = None


@dataclass(frozen=True)
class StatusBlock:
    """A compact summary block for runner, history, and request counters."""
    run_status: str
    raw: int
    max_raw: int
    hist_current: int
    hist_last: int
    kind: str = "status"


@dataclass(frozen=True)
class ActionBlock:
    """A short description of a grouped debugger step or rewind action."""
    verb: str
    boundary: str
    status: str
    raw_delta: int
    count_completed: int = 1
    count_requested: int = 1
    kind: str = "action"


@dataclass(frozen=True)
class RecordBlock:
    """A titled list of named values."""
    title: str
    fields: tuple[Field, ...]
    role: str | None = None
    kind: str = "record"


@dataclass(frozen=True)
class InstructionBlock:
    """A decoded instruction line plus optional argument/explanation text."""
    title: str
    opcode: str | None
    args: tuple[str, ...] = ()
    explanation: str | None = None
    role: str | None = None
    kind: str = "instruction"


@dataclass(frozen=True)
class TransitionBlock:
    """The display form of a raw transition row."""
    title: str
    present: bool
    state: str | None = None
    read_symbol: str | None = None
    write_symbol: str | None = None
    move: int | None = None
    next_state: str | None = None
    role: str | None = None
    kind: str = "transition"


@dataclass(frozen=True)
class TapeCell:
    """One tape cell in a rendered tape window."""
    address: int
    symbol: str


@dataclass(frozen=True)
class TapeBlock:
    """A tape window with a visible head position."""
    title: str
    cells: tuple[TapeCell, ...]
    head: int
    role: str | None = None
    kind: str = "tape"


@dataclass(frozen=True)
class MessageBlock:
    """A free-form message block used for help, warnings, and placeholders."""
    text: str
    title: str | None = None
    role: str | None = None
    kind: str = "message"


@dataclass(frozen=True)
class TableBlock:
    """A simple text table block."""

    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    title: str | None = None
    role: str | None = None
    kind: str = "table"


Block = StatusBlock | ActionBlock | RecordBlock | InstructionBlock | TransitionBlock | TapeBlock | MessageBlock | TableBlock


@dataclass(frozen=True)
class Document:
    """A complete debugger document made of typed presentation blocks."""

    kind: str
    blocks: tuple[Block, ...]
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the document as plain nested dictionaries and tuples."""

        return asdict(self)


__all__ = [
    "ActionBlock",
    "Block",
    "Document",
    "Field",
    "InstructionBlock",
    "MessageBlock",
    "ROLE_HELP",
    "ROLE_INSTRUCTION",
    "ROLE_RAW",
    "ROLE_SEMANTIC",
    "ROLE_SOURCE",
    "ROLE_STATUS",
    "ROLE_TAPE",
    "ROLE_TRANSITION",
    "ROLE_WARNING",
    "RecordBlock",
    "StatusBlock",
    "TableBlock",
    "TapeBlock",
    "TapeCell",
    "TransitionBlock",
]
