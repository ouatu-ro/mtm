"""Debugger presentation builder over typed query rows and help metadata.

This layer turns the query rows into the document blocks that the debugger UI
or tests can render. It is intentionally narrow: the presenter knows how to
shape output, while the queries and help metadata supply the content.
"""

from __future__ import annotations

from .help import COMMAND_SPECS, FIELD_DOCS, OUTPUT_LEGEND, canonical_topic, command_spec
from .presentation import (
    ActionBlock,
    Document,
    Field,
    InstructionBlock,
    MessageBlock,
    RecordBlock,
    ROLE_HELP,
    ROLE_INSTRUCTION,
    ROLE_RAW,
    ROLE_SEMANTIC,
    ROLE_SOURCE,
    ROLE_STATUS,
    ROLE_TAPE,
    ROLE_TRANSITION,
    ROLE_WARNING,
    StatusBlock,
    TableBlock,
    TapeBlock,
    TapeCell,
    TransitionBlock,
)
from .queries import ActionRow, SourceRow, StatusRow, ViewRow, WhereRow


class DebuggerPresenter:
    """Convert debugger query rows into shared presentation documents."""

    def startup_doc(self, *, fixture_name: str, status: StatusRow) -> Document:
        """Build the first document shown when the debugger starts."""

        return Document(
            kind="startup",
            title=f"MTM debugger  fixture={fixture_name}  type `help` for commands",
            blocks=self._status_blocks(status),
        )

    def status_doc(self, row: StatusRow) -> Document:
        """Build the compact status document."""

        return Document(kind="status", blocks=self._status_blocks(row))

    def where_doc(self, row: WhereRow) -> Document:
        """Build the source-location document for ``where`` output."""

        blocks = [*self._source_blocks(row.source), self._transition_block("NEXT ROW", row.next_row)]
        return Document(kind="where", blocks=tuple(blocks))

    def action_doc(self, row: ActionRow) -> Document:
        """Build the document shown after a step or rewind command."""

        blocks = [
            ActionBlock(
                verb=row.verb,
                boundary=row.boundary,
                status=row.status,
                raw_delta=row.raw_delta,
                count_completed=row.count_completed,
                count_requested=row.count_requested,
            ),
            self._raw_block(row.snapshot),
            *self._source_blocks(row.source),
            self._transition_block("NEXT ROW", row.next_row),
        ]
        return Document(kind="action", blocks=tuple(blocks))

    def view_doc(self, row: ViewRow) -> Document:
        """Build the full debugging view with raw, source, tape, and semantic data."""

        blocks = [
            StatusBlock(
                run_status=row.status.snapshot.run_status,
                raw=row.status.snapshot.raw,
                max_raw=row.status.snapshot.max_raw,
                hist_current=row.status.snapshot.hist_current,
                hist_last=row.status.snapshot.hist_last,
            ),
            self._raw_block(row.status.snapshot),
            *self._source_blocks(row.status.source),
            self._transition_block("NEXT ROW", row.next_row),
            self._transition_block("LAST ROW", row.last_row),
            TapeBlock(
                title="RAW TAPE",
                cells=tuple(TapeCell(cell.address, cell.symbol) for cell in row.raw_tape.cells),
                head=row.raw_tape.head,
                role=ROLE_TAPE,
            ),
            *self._semantic_blocks(row),
        ]
        return Document(kind="view", blocks=tuple(blocks))

    def help_doc(self, topic: str | None = None) -> Document | None:
        """Build global or topic-specific help, or return ``None`` for unknown topics."""

        if topic is None or not topic.strip():
            rows = tuple((spec.usage, ", ".join(spec.aliases) or "-", spec.summary) for spec in COMMAND_SPECS)
            legend_blocks = [MessageBlock(text="Visual Legend:", role=ROLE_HELP)]
            legend_blocks.extend(
                RecordBlock(title=label, fields=(Field("body", body),), role=ROLE_HELP) for label, body in OUTPUT_LEGEND
            )
            field_lines = "\n".join(f"  {name:<7}= {doc}" for name, doc in FIELD_DOCS)
            return Document(
                kind="help",
                title="MTM debugger",
                blocks=(
                    TableBlock(headers=("Command", "Alias", "Meaning"), rows=rows, role=ROLE_HELP),
                    *legend_blocks,
                    MessageBlock(text=f"Fields:\n{field_lines}", role=ROLE_HELP),
                ),
            )

        canonical = canonical_topic(topic)
        if canonical is None:
            return None
        if canonical in {"help", "status", "view", "where", "step raw", "step routine", "step instruction", "step block", "step source", "back raw", "back routine", "back instruction", "back block", "back source", "set max-raw", "quit"}:
            spec = command_spec(canonical)
            assert spec is not None
            details = "\n".join(spec.details)
            output_lines = None
            if canonical.startswith("step") or canonical.startswith("back") or canonical in {"status", "view", "where"}:
                output_lines = "\n".join(
                    [
                        "Output:",
                        "  RAW          raw=<step>  head=<raw tape head>  read='<symbol>'  state=<raw TM state>",
                        "  SOURCE       block=<block>  instr=<instruction index>  routine=<lowering routine>  op=<sub-step>",
                        "  INSTRUCTION  OPCODE <ARGS>",
                        "  NEXT ROW     state=<row state>  read='<symbol>'  write='<symbol>'  move=<L|R|S>  next=<next raw state>",
                    ]
                )
            field_lines = "\n".join(f"  {name:<7}= {doc}" for name, doc in FIELD_DOCS)
            blocks = [
                MessageBlock(text=spec.name, role=ROLE_HELP),
                MessageBlock(text=f"usage: {spec.usage}", role=ROLE_HELP),
                MessageBlock(text=f"alias: {', '.join(spec.aliases) if spec.aliases else '-'}", role=ROLE_HELP),
                MessageBlock(text=spec.summary, role=ROLE_HELP),
            ]
            if details:
                blocks.append(MessageBlock(text=details, role=ROLE_HELP))
            if output_lines is not None:
                blocks.append(MessageBlock(text=output_lines, role=ROLE_HELP))
                blocks.append(MessageBlock(text=f"Fields:\n{field_lines}", role=ROLE_HELP))
            return Document(kind="help-topic", blocks=tuple(blocks))
        if canonical in {"step", "back"}:
            if canonical == "step":
                text = "step <boundary> [N]\n\nBoundaries: raw, routine, instruction, block, source\nUse `help step raw` or `help si` for boundary-specific help."
            else:
                text = "back <boundary> [N]\n\nBoundaries: raw, routine, instruction, block, source\nUse `help back raw` or `help bi` for boundary-specific help."
            return Document(kind="help-topic", blocks=(MessageBlock(text=text, role=ROLE_HELP),))
        return None

    def _status_blocks(self, row: StatusRow) -> tuple[object, ...]:
        return (
            StatusBlock(
                run_status=row.snapshot.run_status,
                raw=row.snapshot.raw,
                max_raw=row.snapshot.max_raw,
                hist_current=row.snapshot.hist_current,
                hist_last=row.snapshot.hist_last,
            ),
            self._raw_block(row.snapshot),
            *self._source_blocks(row.source),
        )

    @staticmethod
    def _raw_block(snapshot) -> RecordBlock:
        return RecordBlock(
            title="RAW",
            fields=(
                Field("raw", snapshot.raw, role=ROLE_RAW),
                Field("head", snapshot.head, role=ROLE_RAW),
                Field("read", snapshot.read_symbol, role=ROLE_RAW),
                Field("state", snapshot.state, role=ROLE_RAW),
            ),
            role=ROLE_RAW,
        )

    @staticmethod
    def _source_blocks(source: SourceRow) -> tuple[object, ...]:
        if not source.mapped:
            return (MessageBlock(title="SOURCE", text="<unmapped>", role=ROLE_SOURCE),)
        return (
            RecordBlock(
                title="SOURCE",
                fields=(
                    Field("block", source.block, role=ROLE_SOURCE),
                    Field("instr", source.instr, role=ROLE_SOURCE),
                    Field("routine", source.routine, role=ROLE_SOURCE),
                    Field("op", source.op, role=ROLE_SOURCE),
                ),
                role=ROLE_SOURCE,
            ),
            InstructionBlock(
                title="INSTRUCTION",
                opcode=source.opcode,
                args=source.args,
                explanation=source.explanation,
                role=ROLE_INSTRUCTION,
            ),
        )

    @staticmethod
    def _transition_block(title, row) -> TransitionBlock:
        return TransitionBlock(
            title=title,
            present=row.present,
            state=row.state,
            read_symbol=row.read_symbol,
            write_symbol=row.write_symbol,
            move=row.move,
            next_state=row.next_state,
            role=ROLE_TRANSITION,
        )

    @staticmethod
    def _semantic_blocks(row: ViewRow) -> tuple[object, ...]:
        semantic = row.semantic
        if semantic.status == "available":
            tape = semantic.tape
            assert tape is not None
            return (
                RecordBlock(
                    title="SEMANTIC",
                    fields=(
                        Field("state", semantic.state, role=ROLE_SEMANTIC),
                        Field("head", semantic.head, role=ROLE_SEMANTIC),
                        Field("symbol", semantic.symbol, role=ROLE_SEMANTIC),
                    ),
                    role=ROLE_SEMANTIC,
                ),
                TapeBlock(
                    title="SEM TAPE",
                    cells=tuple(TapeCell(cell.address, cell.symbol) for cell in tape.cells),
                    head=tape.head,
                    role=ROLE_SEMANTIC,
                ),
                RecordBlock(
                    title="REGS",
                    fields=tuple(Field(key, value, role=ROLE_SEMANTIC) for key, value in semantic.registers),
                    role=ROLE_SEMANTIC,
                ),
            )
        if semantic.status == "error":
            return (MessageBlock(title="SEMANTIC", text=f"<decode error: {semantic.decode_error}>", role=ROLE_WARNING),)
        return (MessageBlock(title="SEMANTIC", text="unavailable", role=ROLE_SEMANTIC),)


__all__ = ["DebuggerPresenter"]
