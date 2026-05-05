"""Plain-text debugger renderer over presentation documents.

This renderer turns the structured debugger document model into stable,
line-oriented text for terminals, logs, and tests.
"""

from __future__ import annotations

from ..pretty import table
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


class PlainTextRenderer:
    """Render presentation documents into deterministic line-oriented text.

    This is the lowest-friction renderer: it keeps the same document model as
    the richer terminal view, but emits stable plain text that is easy to read
    in tests, logs, and non-interactive sessions.
    """

    LABEL_WIDTH = 12

    def render(self, document: Document) -> str:
        """Render one presentation document into plain text."""

        lines: list[str] = []
        if document.title is not None:
            lines.append(document.title)
            if document.kind in {"startup", "help"}:
                lines.append("")
        for index, block in enumerate(document.blocks):
            if index and document.kind in {"help", "help-topic"}:
                lines.append("")
            lines.extend(self._render_block(block))
        return "\n".join(lines)

    def _render_block(self, block) -> list[str]:
        if isinstance(block, StatusBlock):
            return [f"{block.run_status}  raw={block.raw}  max_raw={block.max_raw}  hist={block.hist_current}/{block.hist_last}"]
        if isinstance(block, ActionBlock):
            delta = f"{block.raw_delta:+d}" if block.raw_delta else "0"
            count = ""
            if block.count_requested > 1:
                if block.count_completed == block.count_requested:
                    count = f"  count={block.count_completed}"
                else:
                    count = f"  count={block.count_completed}/{block.count_requested}"
            return [f"{block.verb} {block.boundary}  {block.status}{count}  raw_delta={delta}"]
        if isinstance(block, RecordBlock):
            if len(block.fields) == 1 and block.fields[0].key == "body":
                return [self._labeled(block.title, str(block.fields[0].value))]
            body = "  ".join(self._render_field(field) for field in block.fields)
            return [self._labeled(block.title, body)]
        if isinstance(block, InstructionBlock):
            opcode = block.opcode or "<none>"
            args = " ".join(block.args)
            body = opcode if not args else f"{opcode} {args}"
            lines = [self._labeled(block.title, body)]
            if block.explanation:
                lines.append(self._continuation(block.explanation))
            return lines
        if isinstance(block, TransitionBlock):
            if not block.present:
                return [self._labeled(block.title, "<none>")]
            return [
                self._labeled(
                    block.title,
                    "  ".join(
                        [
                            f"state={block.state}",
                            f"read={block.read_symbol!r}",
                            f"write={block.write_symbol!r}",
                            f"move={_format_move(block.move)}",
                            f"next={block.next_state}",
                        ]
                    ),
                )
            ]
        if isinstance(block, TapeBlock):
            cells = []
            for cell in block.cells:
                text = f"{cell.address}:{cell.symbol!r}"
                cells.append(f"[{text}]" if cell.address == block.head else text)
            return [self._labeled(block.title, " ".join(cells))]
        if isinstance(block, MessageBlock):
            if block.title is None:
                return block.text.splitlines() or [""]
            lines = block.text.splitlines()
            if not lines:
                return [self._labeled(block.title, "")]
            rendered = [self._labeled(block.title, lines[0])]
            rendered.extend(self._continuation(line) for line in lines[1:])
            return rendered
        if isinstance(block, TableBlock):
            rows = [list(row) for row in block.rows]
            rendered = table(list(block.headers), rows)
            return [rendered] if block.title is None else [block.title, rendered]
        raise TypeError(f"unsupported block: {type(block)!r}")

    def _render_field(self, field: Field) -> str:
        if field.key in {"read", "write", "symbol"}:
            return f"{field.key}={field.value!r}"
        return f"{field.key}={field.value}"

    def _labeled(self, label: str, body: str) -> str:
        return f"{label:<{self.LABEL_WIDTH}} {body}"

    def _continuation(self, body: str) -> str:
        return f"{'':<{self.LABEL_WIDTH}} {body}"


def _format_move(move: int | None) -> str:
    if move is None:
        return "?"
    if move < 0:
        return "L"
    if move > 0:
        return "R"
    return "S"


__all__ = ["PlainTextRenderer"]
