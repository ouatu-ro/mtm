"""Deterministic text renderers for teaching-facing debugger views."""

from __future__ import annotations

from dataclasses import dataclass
import re

from ..meta_asm import (
    BranchAt,
    BranchCmp,
    CompareGlobalLiteral,
    CompareGlobalLocal,
    CopyGlobalGlobal,
    CopyGlobalToHeadSymbol,
    CopyHeadSymbolTo,
    CopyLocalGlobal,
    FindFirstRule,
    FindHeadCell,
    FindNextRule,
    Goto,
    Halt,
    MoveSimHeadLeft,
    MoveSimHeadRight,
    Seek,
    SeekOneOf,
    Unimplemented,
    WriteGlobal,
)
from ..pretty import table
from ..lowering.source_map import RawTransitionSource
from ..raw_transition_tm import L, R, S, Transition, TransitionKey
from ..semantic_objects import DecodedBandView, UTMSimulatedTape
from .trace import RawTraceGroupStepResult, RawTraceView


def format_source_location(source: RawTransitionSource | None, *, label: str = "source") -> str:
    """Format one lowered raw-row location for teaching output."""

    if source is None:
        return f"{label}: <unmapped>"

    routine = source.routine_name if source.routine_index is None else f"{source.routine_index}:{source.routine_name}"
    instruction = "?" if source.instruction_index is None else str(source.instruction_index)
    lines = [
        f"{label}: block={source.block_label} instruction={instruction} routine={routine} op={source.op_index}",
        f"row: state={source.state!r} read={source.read_symbol!r}",
    ]
    if source.instruction_text is not None:
        lines.append(f"instruction: {source.instruction_text}")
    return "\n".join(lines)


def format_trace_view(
    view: RawTraceView,
    *,
    raw_window: int = 2,
    semantic_window: int = 2,
    blank_symbol: str = ".",
) -> str:
    """Format a raw debugger view plus semantic summary when available."""

    lines = [
        f"snapshot: step={view.snapshot.steps} state={view.snapshot.state!r} head={view.snapshot.head}",
        f"raw tape: {_format_sparse_tape(view.snapshot.tape, head=view.snapshot.head, radius=raw_window, blank_symbol=blank_symbol)}",
    ]
    if view.next_raw_transition_key is None or view.next_raw_transition_row is None:
        lines.append("next raw: <none>")
    else:
        lines.append(f"next raw: {_format_transition(view.next_raw_transition_key, view.next_raw_transition_row)}")

    source = view.next_raw_transition_source
    if source is not None:
        lines.append(format_source_location(source))
    elif view.last_transition_source is not None:
        lines.append(format_source_location(view.last_transition_source, label="last source"))
    else:
        lines.append("source: <unmapped>")

    if view.last_transition is None:
        lines.append("last raw: <none>")
    else:
        lines.append(f"last raw: {_format_last_transition(view.last_transition)}")

    if view.decoded_view is not None:
        lines.extend(_format_decoded_view(view.decoded_view, semantic_window=semantic_window))
    elif view.decode_error is not None:
        lines.append(f"semantic: <decode error: {view.decode_error}>")
    else:
        lines.append("semantic: <not requested>")

    return "\n".join(lines)


def format_group_step_result(
    result: RawTraceGroupStepResult,
    *,
    source: RawTransitionSource | None = None,
) -> str:
    """Format one grouped-step result for concise teaching output."""

    lines = [
        f"group step: status={result.status} raw_steps={result.raw_steps}",
        f"snapshot: step={result.snapshot.steps} state={result.snapshot.state!r} head={result.snapshot.head}",
    ]
    if source is not None:
        lines.append(format_source_location(source))
    return "\n".join(lines)


def _format_transition(key: TransitionKey, row: Transition) -> str:
    next_state, write_symbol, move = row
    state, read_symbol = key
    return f"({state!r}, {read_symbol!r}) -> ({next_state!r}, {write_symbol!r}, {_format_move(move)})"


def _format_last_transition(transition) -> str:
    return _format_transition(
        transition.key,
        (transition.next_state, transition.write_symbol, transition.move),
    )


def _format_decoded_view(view: DecodedBandView, *, semantic_window: int) -> list[str]:
    registers = view.registers
    tmp_bits = "".join(registers.tmp_bits) or "-"
    return [
        f"semantic: state={view.current_state!r} head={view.simulated_head}",
        f"semantic tape: {_format_semantic_tape(view.simulated_tape, radius=semantic_window)}",
        "registers: "
        f"cur={registers.cur_state!r} read={registers.cur_symbol!r} write={registers.write_symbol!r} "
        f"next={registers.next_state!r} move={_format_move(registers.move_dir)} cmp={registers.cmp_flag!r} tmp={tmp_bits!r}",
    ]


def _format_semantic_tape(tape: UTMSimulatedTape, *, radius: int) -> str:
    cells: dict[int, str] = {
        **{index - len(tape.left_band): symbol for index, symbol in enumerate(tape.left_band)},
        **{index: symbol for index, symbol in enumerate(tape.right_band)},
    }
    return _format_sparse_tape(cells, head=tape.head, radius=radius, blank_symbol=tape.blank)


def _format_sparse_tape(tape, *, head: int, radius: int, blank_symbol: str) -> str:
    cells = []
    for address in range(head - radius, head + radius + 1):
        symbol = tape.get(address, blank_symbol)
        cell = f"{address}:{symbol!r}"
        cells.append(f"[{cell}]" if address == head else cell)
    return " ".join(cells)


def _format_move(move: int) -> str:
    if move == L:
        return "L"
    if move == R:
        return "R"
    if move == S:
        return "S"
    return str(move)

@dataclass(frozen=True)
class DebuggerRunnerSummary:
    run_status: str
    raw: int
    max_raw: int
    hist_current: int
    hist_last: int
    state: str
    head: int
    read_symbol: str


@dataclass(frozen=True)
class DebuggerLocationSummary:
    mapped: bool
    block: str | None
    instr: str | None
    routine: str | None
    op: int | None
    instruction_text: str | None
    instruction_help: str | None


@dataclass(frozen=True)
class DebuggerTransitionSummary:
    present: bool
    state: str | None
    read_symbol: str | None
    write_symbol: str | None
    move: str | None
    next_state: str | None


@dataclass(frozen=True)
class DebuggerSemanticSummary:
    status: str
    state: str | None = None
    head: int | None = None
    symbol: str | None = None
    tape: str | None = None
    cur: str | None = None
    read: str | None = None
    write: str | None = None
    next: str | None = None
    move: str | None = None
    cmp: str | None = None
    tmp: str | None = None
    decode_error: str | None = None


@dataclass(frozen=True)
class DebuggerActionSummary:
    verb: str
    boundary: str
    status: str
    raw_delta: int
    runner: DebuggerRunnerSummary
    location: DebuggerLocationSummary
    next_row: DebuggerTransitionSummary
    count_completed: int = 1
    count_requested: int = 1


@dataclass(frozen=True)
class DebuggerViewSummary:
    runner: DebuggerRunnerSummary
    location: DebuggerLocationSummary
    next_row: DebuggerTransitionSummary
    last_row: DebuggerTransitionSummary
    raw_tape: str
    semantic: DebuggerSemanticSummary


class DebuggerRenderer:
    """Plain-text renderer for the debugger REPL surface."""

    def __init__(self, *, color: bool = False) -> None:
        self.color = color

    def render_startup(self, *, fixture_name: str, runner: DebuggerRunnerSummary, location: DebuggerLocationSummary) -> str:
        status_body = self.render_status(runner=runner, location=location)
        return "\n".join([
            f"MTM debugger  fixture={fixture_name}  type `help` for commands",
            "",
            status_body,
        ])

    def render_status(self, *, runner: DebuggerRunnerSummary, location: DebuggerLocationSummary) -> str:
        lines = [
            self._render_compact_status(runner),
            self._render_raw_line(runner),
        ]
        lines.extend(self._render_location_lines(location))
        return "\n".join(lines)

    def render_where(
        self,
        *,
        location: DebuggerLocationSummary,
        next_row: DebuggerTransitionSummary,
    ) -> str:
        lines = self._render_location_lines(location)
        lines.append(self._render_transition_line("NEXT ROW", next_row))
        return "\n".join(lines)

    def render_action(self, summary: DebuggerActionSummary) -> str:
        delta = f"{summary.raw_delta:+d}" if summary.raw_delta else "0"
        count_part = ""
        if summary.count_requested > 1:
            if summary.count_completed == summary.count_requested:
                count_part = f"  count={summary.count_completed}"
            else:
                count_part = f"  count={summary.count_completed}/{summary.count_requested}"
        lines = [
            f"{summary.verb} {summary.boundary}  {summary.status}{count_part}  raw_delta={delta}",
            self._render_raw_line(summary.runner),
        ]
        lines.extend(self._render_location_lines(summary.location))
        lines.append(self._render_transition_line("NEXT ROW", summary.next_row))
        return "\n".join(lines)

    def render_view(self, summary: DebuggerViewSummary) -> str:
        lines = [
            self._render_compact_status(summary.runner),
            self._render_raw_line(summary.runner),
        ]
        lines.extend(self._render_location_lines(summary.location))
        lines.append(self._render_transition_line("NEXT ROW", summary.next_row))
        lines.append(self._render_transition_line("LAST ROW", summary.last_row))
        lines.append("")
        lines.append(self._render_labeled("RAW TAPE", summary.raw_tape))
        lines.append("")
        lines.extend(self._render_semantic(summary.semantic))
        return "\n".join(lines)

    def render_help(self) -> str:
        return "\n".join([
            "MTM debugger",
            "",
            table(
                ["Command", "Alias", "Meaning"],
                [
                    ["status", "st", "Show compact runner status"],
                    ["view", "v", "Show raw + source + semantic trace view"],
                    ["where", "w", "Show current lowered source location"],
                    ["step raw [N]", "s", "Step one or N raw TM transitions"],
                    ["step routine [N]", "sr", "Step to the next N lowering routines"],
                    ["step instruction [N]", "si", "Step to the next N Meta-ASM instructions"],
                    ["step block [N]", "sb", "Step to the next N Meta-ASM blocks"],
                    ["step source [N]", "ss", "Step one or N simulated source-TM transitions"],
                    ["back raw [N]", "b", "Rewind one or N raw TM transitions"],
                    ["back routine [N]", "br", "Rewind to the previous N lowering routines"],
                    ["back instruction [N]", "bi", "Rewind to the previous N Meta-ASM instructions"],
                    ["back block [N]", "bb", "Rewind to the previous N Meta-ASM blocks"],
                    ["back source [N]", "bs", "Rewind to the previous N simulated source-TM transitions"],
                    ["set max-raw N", "-", "Set grouped-step raw transition guard"],
                    ["help", "h, ?", "Show this help"],
                    ["quit", "q", "Exit debugger"],
                ],
            ),
            "",
            "Visual Legend:",
            self._render_labeled("RAW", "raw=<step>  head=<raw tape head>  read='<symbol>'  state=<raw TM state>"),
            self._render_labeled("SOURCE", "block=<block>  instr=<instruction index>  routine=<lowering routine>  op=<sub-step>"),
            self._render_labeled("INSTRUCTION", "OPCODE <ARGS>"),
            self._render_continuation("Human explanation of what that Meta-ASM instruction does."),
            self._render_labeled("NEXT ROW", "state=<row state>  read='<symbol>'  write='<symbol>'  move=<L|R|S>  next=<next raw state>"),
            self._render_labeled("LAST ROW", "Previously executed raw TM transition row (view only)"),
            "",
            "Fields:",
            "  raw     = Absolute raw transition index in debugger history",
            "  head    = Raw tape head position",
            "  read    = Symbol currently under the raw tape head",
            "  block   = Meta-ASM block label",
            "  instr   = Meta-ASM instruction index within the current block (`setup` before the first instruction)",
            "  routine = Lowering routine derived from that Meta-ASM instruction",
            "  op      = Lowering sub-operation index within the routine",
        ])

    def render_command_help(self, topic: str) -> str | None:
        canonical = _canonical_help_topic(topic)
        if canonical is None:
            return None
        return _COMMAND_HELP[canonical]

    @staticmethod
    def render_set_max_raw(value: int) -> str:
        return f"max_raw={value}"

    def _render_compact_status(self, runner: DebuggerRunnerSummary) -> str:
        return f"{runner.run_status}  raw={runner.raw}  max_raw={runner.max_raw}  hist={runner.hist_current}/{runner.hist_last}"

    def _render_raw_line(self, runner: DebuggerRunnerSummary) -> str:
        return self._render_labeled(
            "RAW",
            f"raw={runner.raw}  head={runner.head}  read={runner.read_symbol!r}  state={runner.state}",
        )

    def _render_location_lines(self, location: DebuggerLocationSummary) -> list[str]:
        if not location.mapped:
            return [self._render_labeled("SOURCE", "<unmapped>")]
        lines = [self._render_labeled(
            "SOURCE",
            f"block={location.block}  instr={location.instr}  routine={location.routine}  op={location.op}",
        )]
        if location.instruction_text is not None:
            lines.append(self._render_labeled("INSTRUCTION", location.instruction_text))
        if location.instruction_help is not None:
            lines.append(self._render_continuation(location.instruction_help))
        return lines

    def _render_transition(self, transition: DebuggerTransitionSummary) -> str:
        if not transition.present:
            return "<none>"
        return (
            f"state={transition.state}  read={transition.read_symbol!r}  "
            f"write={transition.write_symbol!r}  move={transition.move}  next={transition.next_state}"
        )

    def _render_transition_line(self, label: str, transition: DebuggerTransitionSummary) -> str:
        return self._render_labeled(label, self._render_transition(transition))

    def _render_semantic(self, semantic: DebuggerSemanticSummary) -> list[str]:
        if semantic.status == "available":
            return [
                self._render_labeled("SEMANTIC", f"state={semantic.state}  head={semantic.head}  symbol={semantic.symbol!r}"),
                self._render_labeled("SEM TAPE", semantic.tape or "<none>"),
                self._render_labeled(
                    "REGS",
                    f"cur={semantic.cur}  read={semantic.read!r}  write={semantic.write!r}  "
                    f"next={semantic.next}  move={semantic.move}  cmp={semantic.cmp!r}  tmp={semantic.tmp!r}",
                ),
            ]
        if semantic.status == "error":
            return [self._render_labeled("SEMANTIC", f"<decode error: {semantic.decode_error}>")]
        return [self._render_labeled("SEMANTIC", "unavailable")]

    def _render_labeled(self, label: str, body: str) -> str:
        return f"{label:<12} {body}"

    def _render_continuation(self, body: str) -> str:
        return f"{'':12} {body}"

    def format_output(self, text: str) -> str:
        """Apply optional ANSI styling to already-rendered plain text."""

        if not self.color:
            return text

        styled_lines: list[str] = []
        for line in text.splitlines():
            styled = line
            if line.startswith("MTM debugger"):
                styled = self._ansi("1;36") + line + self._ansi("0")
            elif re.match(r"^(running|halted|stuck)\b", line):
                styled = self._color_status_line(line)
            elif re.match(
                r"^(step|back) [a-z]+  (stepped|rewound|halted|stuck|max_raw|unmapped|at_start)\b",
                line,
            ):
                styled = self._color_action_line(line)
            elif self._starts_with_label(line, "RAW"):
                styled = self._color_labeled_line(line, "RAW", {"raw", "head", "read", "state"})
            elif self._starts_with_label(line, "SOURCE"):
                styled = self._color_labeled_line(line, "SOURCE", {"block", "instr", "routine", "op"})
            elif self._starts_with_label(line, "INSTRUCTION"):
                styled = self._color_instruction_line(line)
            elif self._starts_with_label(line, "NEXT ROW"):
                styled = self._color_labeled_line(line, "NEXT ROW", {"state", "read", "write", "move", "next"})
            elif self._starts_with_label(line, "LAST ROW"):
                styled = self._color_labeled_line(line, "LAST ROW", {"state", "read", "write", "move", "next"})
            elif self._starts_with_label(line, "RAW TAPE"):
                styled = self._color_label_only(line, "RAW TAPE")
            elif self._starts_with_label(line, "SEMANTIC"):
                styled = self._color_semantic_line(line)
            elif self._starts_with_label(line, "SEM TAPE"):
                styled = self._color_label_only(line, "SEM TAPE")
            elif self._starts_with_label(line, "REGS"):
                styled = self._color_labeled_line(line, "REGS", {"cur", "read", "write", "next", "move", "cmp", "tmp"})
            elif line.startswith("Visual Legend:") or line.startswith("Fields:"):
                styled = self._ansi("1;36") + line + self._ansi("0")
            elif line.startswith("            "):
                styled = self._ansi("36") + line + self._ansi("0")
            styled_lines.append(styled)
        return "\n".join(styled_lines)

    def _color_status_line(self, line: str) -> str:
        status, rest = line.split("  ", 1)
        return f"{self._style_status(status)}  {rest}"

    def _color_action_line(self, line: str) -> str:
        parts = line.split("  ")
        head = f"{self._ansi('1')}{parts[0]}{self._ansi('0')}"
        status = self._style_status(parts[1]) if len(parts) > 1 else ""
        tail = parts[2] if len(parts) > 2 else ""
        return "  ".join([part for part in (head, status, tail) if part])

    def _color_semantic_line(self, line: str) -> str:
        colored = self._color_label_only(line, "SEMANTIC")
        if "unavailable" in line or "<decode error:" in line:
            return f"{self._ansi('1;33')}{colored}{self._ansi('0')}"
        return self._color_keys(colored, {"state", "head", "symbol"})

    def _color_keys(self, line: str, keys: set[str]) -> str:
        styled = line
        for key in keys:
            styled = re.sub(rf"\b{re.escape(key)}=", f"{self._ansi('1;36')}{key}{self._ansi('0')}=", styled)
        return styled

    def _color_labeled_line(self, line: str, label: str, keys: set[str]) -> str:
        return self._color_keys(self._color_label_only(line, label), keys)

    def _color_label_only(self, line: str, label: str) -> str:
        prefix = f"{label:<12}"
        if not line.startswith(prefix):
            return line
        return f"{self._ansi('1;35')}{prefix}{self._ansi('0')}{line[len(prefix):]}"

    def _color_instruction_line(self, line: str) -> str:
        prefix = f"{'INSTRUCTION':<12}"
        if not line.startswith(prefix):
            return line
        body = line[len(prefix):]
        stripped = body.strip()
        if not stripped:
            return self._color_label_only(line, "INSTRUCTION")
        opcode, _, rest = stripped.partition(" ")
        colored_body = f"{self._ansi('1;33')}{opcode}{self._ansi('0')}"
        if rest:
            colored_body += f" {rest}"
        return f"{self._ansi('1;35')}{prefix}{self._ansi('0')} {colored_body}"

    def _style_status(self, status: str) -> str:
        color = {
            "running": "1;32",
            "stepped": "1;32",
            "rewound": "1;36",
            "max_raw": "1;33",
            "unmapped": "1;33",
            "stuck": "1;31",
            "halted": "1;35",
            "at_start": "2;36",
        }.get(status, "1;37")
        return f"{self._ansi(color)}{status}{self._ansi('0')}"

    @staticmethod
    def _starts_with_label(line: str, label: str) -> bool:
        return line.startswith(f"{label:<12}")

    @staticmethod
    def _ansi(code: str) -> str:
        return f"\033[{code}m"


def explain_meta_instruction(instruction) -> str | None:
    if instruction is None:
        return None
    match instruction:
        case Goto(label=label):
            return f"Jump to block {label}."
        case Halt():
            return "Stop the universal machine."
        case Seek(marker=marker, direction=direction):
            return f"Move {direction} until marker {marker} is under the head."
        case SeekOneOf(markers=markers, direction=direction):
            return f"Move {direction} until one of {', '.join(markers)} is under the head."
        case FindFirstRule():
            return "Seek to the first encoded rule in the rule table."
        case FindNextRule():
            return "Advance to the next encoded rule in the rule table."
        case FindHeadCell():
            return "Seek to the simulated source-tape head cell."
        case CompareGlobalLocal(global_marker=global_marker, local_marker=local_marker, width=width):
            return f"Compare register {global_marker} against local field {local_marker} over {width} bits."
        case CompareGlobalLiteral(global_marker=global_marker, literal_bits=literal_bits):
            return f"Compare register {global_marker} against literal bits {''.join(literal_bits)}."
        case BranchCmp(label_equal=label_equal, label_not_equal=label_not_equal):
            return f"If the last compare matched, jump to {label_equal}; otherwise jump to {label_not_equal}."
        case CopyLocalGlobal(local_marker=local_marker, global_marker=global_marker, width=width):
            return f"Copy {width} bits from local field {local_marker} into register {global_marker}."
        case CopyGlobalGlobal(src_marker=src_marker, dst_marker=dst_marker, width=width):
            return f"Copy {width} bits from register {src_marker} into register {dst_marker}."
        case CopyHeadSymbolTo(global_marker=global_marker, width=width):
            return f"Copy the simulated tape symbol under the head into register {global_marker} ({width} bits)."
        case CopyGlobalToHeadSymbol(global_marker=global_marker, width=width):
            return f"Write register {global_marker} back into the simulated tape symbol under the head ({width} bits)."
        case WriteGlobal(global_marker=global_marker, literal_bits=literal_bits):
            return f"Write literal bits {''.join(literal_bits)} into register {global_marker}."
        case MoveSimHeadLeft():
            return "Move the simulated source-tape head one cell to the left."
        case MoveSimHeadRight():
            return "Move the simulated source-tape head one cell to the right."
        case BranchAt(marker=marker, label_true=label_true, label_false=label_false):
            return f"If the current marker is {marker}, jump to {label_true}; otherwise jump to {label_false}."
        case Unimplemented(note=note):
            return note
        case _:
            return None


def _canonical_help_topic(topic: str) -> str | None:
    normalized = " ".join(topic.strip().split())
    if not normalized:
        return "help"
    return _HELP_TOPIC_ALIASES.get(normalized)


_HELP_TOPIC_ALIASES = {
    "status": "status",
    "st": "status",
    "view": "view",
    "v": "view",
    "where": "where",
    "w": "where",
    "step": "step",
    "step raw": "step raw",
    "s": "step raw",
    "step routine": "step routine",
    "sr": "step routine",
    "step instruction": "step instruction",
    "si": "step instruction",
    "step block": "step block",
    "sb": "step block",
    "step source": "step source",
    "ss": "step source",
    "back": "back",
    "back raw": "back raw",
    "b": "back raw",
    "back routine": "back routine",
    "br": "back routine",
    "back instruction": "back instruction",
    "bi": "back instruction",
    "back block": "back block",
    "bb": "back block",
    "back source": "back source",
    "bs": "back source",
    "set": "set",
    "set max-raw": "set max-raw",
    "help": "help",
    "h": "help",
    "?": "help",
    "quit": "quit",
    "q": "quit",
}


def _help_labeled(label: str, body: str) -> str:
    return f"{label:<12} {body}"


def _help_cont(body: str) -> str:
    return f"{'':12} {body}"


_HELP_OUTPUT_STATUS = [
    _help_labeled("RAW", "raw=<step>  head=<raw tape head>  read='<symbol>'  state=<raw TM state>"),
    _help_labeled("SOURCE", "block=<block>  instr=<instruction index>  routine=<lowering routine>  op=<sub-step>"),
    _help_labeled("INSTRUCTION", "OPCODE <ARGS>"),
    _help_cont("Human explanation of what that Meta-ASM instruction does."),
]

_HELP_OUTPUT_STEP = [
    *_HELP_OUTPUT_STATUS,
    _help_labeled("NEXT ROW", "state=<row state>  read='<symbol>'  write='<symbol>'  move=<L|R|S>  next=<next raw state>"),
]

_HELP_OUTPUT_VIEW = [
    *_HELP_OUTPUT_STEP,
    _help_labeled("LAST ROW", "Previously executed raw TM transition row"),
    _help_labeled("RAW TAPE", "Small raw tape window around the current head position"),
    _help_labeled("SEMANTIC", "Decoded simulated-machine state when semantic decoding is available"),
    _help_labeled("SEM TAPE", "Small simulated source-tape window around the decoded head"),
    _help_labeled("REGS", "Decoded UTM working registers used to simulate the source machine"),
]

_HELP_COMMON_FIELDS = [
    "Fields:",
    "  raw     = Absolute raw transition index in debugger history",
    "  head    = Raw tape head position",
    "  read    = Symbol currently under the raw tape head",
    "  state   = Raw TM control state (or row key state on NEXT/LAST ROW)",
    "  block   = Meta-ASM block label",
    "  instr   = Meta-ASM instruction index within the current block (`setup` before the first instruction)",
    "  routine = Lowering routine derived from that Meta-ASM instruction",
    "  op      = Lowering sub-operation index within the routine",
    "  move    = Raw TM head movement: L, R, or S",
    "  next    = Raw TM state reached after that row fires",
]


_COMMAND_HELP = {
    "status": "\n".join([
        "status",
        "alias: st",
        "Show the compact runner summary for the current snapshot.",
        "Output:",
        *_HELP_OUTPUT_STATUS,
        "",
        *_HELP_COMMON_FIELDS,
    ]),
    "view": "\n".join([
        "view",
        "alias: v",
        "Show the detailed diagnostic view for the current snapshot.",
        "Output:",
        *_HELP_OUTPUT_VIEW,
        "",
        *_HELP_COMMON_FIELDS,
    ]),
    "where": "\n".join([
        "where",
        "alias: w",
        "Show only the current lowered source location.",
        "Output:",
        _help_labeled("SOURCE", "block=<block>  instr=<instruction index>  routine=<lowering routine>  op=<sub-step>"),
        _help_labeled("INSTRUCTION", "OPCODE <ARGS>"),
        _help_cont("Human explanation of what that Meta-ASM instruction does."),
        _help_labeled("NEXT ROW", "state=<row state>  read='<symbol>'  write='<symbol>'  move=<L|R|S>  next=<next raw state>"),
        "",
        *_HELP_COMMON_FIELDS[0:1],
        *_HELP_COMMON_FIELDS[4:],
    ]),
    "step": "\n".join([
        "step <boundary> [N]",
        "Boundaries: raw, routine, instruction, block, source",
        "Move forward until the requested boundary is reached or a guard condition stops execution.",
        "Optional N repeats that boundary step N times, stopping early on halted, stuck, max_raw, or unmapped.",
        "Use `help step raw`, `help step instruction`, etc. for boundary-specific details.",
    ]),
    "step raw": "\n".join([
        "step raw",
        "alias: s",
        "Advance by exactly one raw TM transition.",
        "You can pass N, as in `s 10` or `step raw 10`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        *_HELP_COMMON_FIELDS,
    ]),
    "step routine": "\n".join([
        "step routine",
        "alias: sr",
        "Advance until the next lowering routine starts.",
        "You can pass N, as in `sr 3`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Stop when execution reaches the start of the next lowering routine.",
    ]),
    "step instruction": "\n".join([
        "step instruction",
        "alias: si",
        "Advance until the next Meta-ASM instruction starts.",
        "You can pass N, as in `si 5`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Stop when execution reaches the start of the next Meta-ASM instruction.",
    ]),
    "step block": "\n".join([
        "step block",
        "alias: sb",
        "Advance until the next Meta-ASM block starts.",
        "You can pass N, as in `sb 2`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Stop when execution reaches the start of the next Meta-ASM block.",
    ]),
    "step source": "\n".join([
        "step source",
        "alias: ss",
        "Advance until the next simulated source-TM transition starts.",
        "You can pass N, as in `ss 4`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Stop when execution reaches the start of the next simulated source-machine transition.",
    ]),
    "back": "\n".join([
        "back <boundary> [N]",
        "Boundaries: raw, routine, instruction, block, source",
        "Move backward through retained history to the previous boundary start.",
        "Optional N repeats that rewind N times, stopping early at the start of history or another boundary stop condition.",
        "Use `help back raw`, `help back instruction`, etc. for boundary-specific details.",
    ]),
    "back raw": "\n".join([
        "back raw",
        "alias: b",
        "Rewind by exactly one raw TM transition in retained history.",
        "You can pass N, as in `b 10` or `back raw 10`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Move the debugger cursor back by one retained raw transition snapshot.",
    ]),
    "back routine": "\n".join([
        "back routine",
        "alias: br",
        "Rewind to the previous lowering routine start.",
        "You can pass N, as in `br 3`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Move to the previous retained lowering routine start in history.",
    ]),
    "back instruction": "\n".join([
        "back instruction",
        "alias: bi",
        "Rewind to the previous Meta-ASM instruction start.",
        "You can pass N, as in `bi 5`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Move to the previous retained Meta-ASM instruction start in history.",
    ]),
    "back block": "\n".join([
        "back block",
        "alias: bb",
        "Rewind to the previous Meta-ASM block start.",
        "You can pass N, as in `bb 2`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Move to the previous retained Meta-ASM block start in history.",
    ]),
    "back source": "\n".join([
        "back source",
        "alias: bs",
        "Rewind to the previous simulated source-TM transition start.",
        "You can pass N, as in `bs 4`, to repeat the command.",
        "Output:",
        *_HELP_OUTPUT_STEP,
        "",
        "Boundary meaning:",
        "  Move to the previous retained simulated source-machine transition start.",
    ]),
    "set": "\n".join([
        "set max-raw N",
        "Change the grouped-step raw-transition guard.",
        "Grouped commands like `step instruction` stop with status `max_raw` after N raw transitions if the requested boundary was not reached.",
    ]),
    "help": "\n".join([
        "help [topic]",
        "aliases: h, ?",
        "Show the command table, or detailed help for one command or alias.",
        "Examples: `help step instruction`, `help si`, `help set`.",
    ]),
    "quit": "\n".join([
        "quit",
        "alias: q",
        "Exit the debugger shell.",
    ]),
}


__all__ = [
    "DebuggerActionSummary",
    "DebuggerLocationSummary",
    "DebuggerRenderer",
    "DebuggerRunnerSummary",
    "DebuggerSemanticSummary",
    "DebuggerTransitionSummary",
    "DebuggerViewSummary",
    "explain_meta_instruction",
    "format_group_step_result",
    "format_source_location",
    "format_trace_view",
]
