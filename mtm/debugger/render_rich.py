"""Rich-based debugger renderer over presentation documents.

This renderer uses Rich to preserve the same document model while adding color
and terminal layout when the output is meant for an interactive shell.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

from .presentation import (
    ActionBlock,
    Document,
    Field,
    InstructionBlock,
    MessageBlock,
    RecordBlock,
    StatusBlock,
    TableBlock,
    TapeBlock,
    TransitionBlock,
)


class RichRenderer:
    """Render presentation documents into ANSI-colored terminal text with Rich.

    It preserves the same structured debugger document model as the plain-text
    renderer, but adds color and richer terminal layout when a TTY is present.
    """

    LABEL_WIDTH = 12

    def __init__(self, *, color: bool = True) -> None:
        self.color = color

    def render(self, document: Document) -> str:
        """Render one presentation document to ANSI-colored terminal text."""

        buffer = StringIO()
        console = Console(
            file=buffer,
            force_terminal=self.color,
            color_system="truecolor" if self.color else None,
            no_color=not self.color,
            highlight=False,
            soft_wrap=False,
            width=240,
        )
        parts = []
        if document.title is not None:
            title = Text(document.title, style="bold cyan" if self.color else "")
            parts.append(title)
            if document.kind in {"startup", "help"}:
                parts.append(Text(""))
        for index, block in enumerate(document.blocks):
            if index and document.kind in {"help", "help-topic"}:
                parts.append(Text(""))
            parts.extend(self._render_block(block))
        console.print(Group(*parts))
        return buffer.getvalue().rstrip("\n")

    def _render_block(self, block) -> list[object]:
        if isinstance(block, StatusBlock):
            return [Text.assemble(
                (block.run_status, _status_style(block.run_status, self.color)),
                (f"  raw={block.raw}  max_raw={block.max_raw}  hist={block.hist_current}/{block.hist_last}", ""),
            )]
        if isinstance(block, ActionBlock):
            delta = f"{block.raw_delta:+d}" if block.raw_delta else "0"
            count = ""
            if block.count_requested > 1:
                count = (
                    f"  count={block.count_completed}"
                    if block.count_completed == block.count_requested
                    else f"  count={block.count_completed}/{block.count_requested}"
                )
            return [Text.assemble(
                (f"{block.verb} {block.boundary}", "bold"),
                ("  ", ""),
                (block.status, _status_style(block.status, self.color)),
                (f"{count}  raw_delta={delta}", ""),
            )]
        if isinstance(block, RecordBlock):
            if len(block.fields) == 1 and block.fields[0].key == "body":
                return [self._labeled(block.title, str(block.fields[0].value), label_style=_label_style(block.title, self.color))]
            body = Text()
            for index, field in enumerate(block.fields):
                if index:
                    body.append("  ")
                body.append_text(self._render_field(field))
            return [self._labeled_text(block.title, body, label_style=_label_style(block.title, self.color))]
        if isinstance(block, InstructionBlock):
            opcode = block.opcode or "<none>"
            body = Text()
            body.append(opcode, style="bold yellow" if self.color else "")
            if block.args:
                body.append(" ")
                body.append(" ".join(block.args))
            lines: list[object] = [self._labeled_text(block.title, body, label_style=_label_style(block.title, self.color))]
            if block.explanation:
                lines.append(self._continuation(block.explanation, style="cyan" if self.color else ""))
            return lines
        if isinstance(block, TransitionBlock):
            if not block.present:
                return [self._labeled(block.title, "<none>", label_style=_label_style(block.title, self.color))]
            body = Text()
            for index, part in enumerate((
                ("state", block.state),
                ("read", repr(block.read_symbol)),
                ("write", repr(block.write_symbol)),
                ("move", _format_move(block.move)),
                ("next", block.next_state),
            )):
                key, value = part
                if index:
                    body.append("  ")
                body.append(f"{key}=", style="bold cyan" if self.color else "")
                body.append(str(value))
            return [self._labeled_text(block.title, body, label_style=_label_style(block.title, self.color))]
        if isinstance(block, TapeBlock):
            body = Text()
            for index, cell in enumerate(block.cells):
                if index:
                    body.append(" ")
                text = f"{cell.address}:{cell.symbol!r}"
                if cell.address == block.head and self.color:
                    body.append(f"[{text}]", style="bold reverse")
                else:
                    body.append(f"[{text}]" if cell.address == block.head else text)
            return [self._labeled_text(block.title, body, label_style=_label_style(block.title, self.color))]
        if isinstance(block, MessageBlock):
            lines = block.text.splitlines() or [""]
            if block.title is None:
                return [Text(line, style=_message_style(block, self.color)) for line in lines]
            rendered: list[object] = [
                self._labeled(block.title, lines[0], label_style=_label_style(block.title, self.color), body_style=_message_style(block, self.color))
            ]
            rendered.extend(self._continuation(line, style=_message_style(block, self.color)) for line in lines[1:])
            return rendered
        if isinstance(block, TableBlock):
            table_block = Table(show_header=True, header_style="bold", box=None, pad_edge=False, expand=False)
            for header in block.headers:
                table_block.add_column(header)
            for row in block.rows:
                table_block.add_row(*row)
            if block.title is not None:
                return [Text(block.title, style="bold cyan" if self.color else ""), table_block]
            return [table_block]
        raise TypeError(f"unsupported block: {type(block)!r}")

    def _render_field(self, field: Field) -> Text:
        value = repr(field.value) if field.key in {"read", "write", "symbol"} else str(field.value)
        text = Text()
        text.append(f"{field.key}=", style="bold cyan" if self.color else "")
        text.append(value)
        return text

    def _labeled(self, label: str, body: str, *, label_style: str = "", body_style: str = "") -> Text:
        text = Text()
        text.append(f"{label:<{self.LABEL_WIDTH}}", style=label_style)
        text.append(" ")
        text.append(body, style=body_style)
        return text

    def _labeled_text(self, label: str, body: Text, *, label_style: str = "") -> Text:
        text = Text()
        text.append(f"{label:<{self.LABEL_WIDTH}}", style=label_style)
        text.append(" ")
        text.append_text(body)
        return text

    def _continuation(self, body: str, *, style: str = "") -> Text:
        text = Text()
        text.append(f"{'':<{self.LABEL_WIDTH}} ")
        text.append(body, style=style)
        return text


def _label_style(label: str, color: bool) -> str:
    if not color:
        return ""
    if label in {"INSTRUCTION"}:
        return "bold yellow"
    if label in {"RAW", "SOURCE", "NEXT ROW", "LAST ROW", "RAW TAPE", "SEMANTIC", "SEM TAPE", "REGS"}:
        return "bold magenta"
    return "bold cyan"


def _message_style(block: MessageBlock, color: bool) -> str:
    if not color:
        return ""
    if block.role == "warning":
        return "yellow"
    return ""


def _status_style(status: str, color: bool) -> str:
    if not color:
        return ""
    return {
        "running": "bold green",
        "stepped": "bold green",
        "rewound": "bold cyan",
        "max_raw": "bold yellow",
        "unmapped": "bold yellow",
        "halted": "bold magenta",
        "stuck": "bold red",
        "at_start": "cyan",
    }.get(status, "bold")


def _format_move(move: int | None) -> str:
    if move is None:
        return "?"
    if move < 0:
        return "L"
    if move > 0:
        return "R"
    return "S"


__all__ = ["RichRenderer"]
