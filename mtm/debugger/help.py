"""Command and field metadata for the debugger REPL.

The debugger uses these tables as the single source of truth for command help,
field glossaries, and topic aliases. Keeping them together makes the help text
consistent with the presenter and easy to update as the REPL evolves.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    """A debugger command with its aliases, usage, and explanatory text."""

    name: str
    aliases: tuple[str, ...]
    usage: str
    summary: str
    details: tuple[str, ...]


COMMAND_SPECS = (
    CommandSpec(
        name="status",
        aliases=("st",),
        usage="status",
        summary="Show compact runner status.",
        details=(
            "Displays run status, raw step/history counters, current lowered state, current source location, and active instruction.",
        ),
    ),
    CommandSpec(
        name="view",
        aliases=("v",),
        usage="view",
        summary="Show raw + source + semantic trace view.",
        details=(
            "Includes the compact status layers, next/last raw rows, a raw tape window, and semantic decode when available.",
        ),
    ),
    CommandSpec(
        name="where",
        aliases=("w",),
        usage="where",
        summary="Show current lowered source location.",
        details=(
            "Shows the current Meta-ASM source location, active instruction, and the next raw row that would execute.",
        ),
    ),
    CommandSpec(
        name="step raw",
        aliases=("s",),
        usage="step raw [N]",
        summary="Advance by exactly one raw TM transition.",
        details=(
            "Use this when you want to inspect the lowered machine row by row.",
            "You can pass N, as in `s 10` or `step raw 10`, to repeat the command.",
        ),
    ),
    CommandSpec(
        name="step routine",
        aliases=("sr",),
        usage="step routine [N]",
        summary="Advance to the next lowering routine boundary.",
        details=(
            "Stops when the next lowered routine begins, or earlier if the runner halts, gets stuck, or hits max-raw.",
        ),
    ),
    CommandSpec(
        name="step instruction",
        aliases=("si",),
        usage="step instruction [N]",
        summary="Advance to the next Meta-ASM instruction boundary.",
        details=(
            "Useful when you want source-level stepping without stopping on every lowered raw row.",
        ),
    ),
    CommandSpec(
        name="step block",
        aliases=("sb",),
        usage="step block [N]",
        summary="Advance to the next Meta-ASM block boundary.",
        details=(),
    ),
    CommandSpec(
        name="step source",
        aliases=("ss",),
        usage="step source [N]",
        summary="Advance to the next simulated source-TM transition.",
        details=(),
    ),
    CommandSpec(
        name="back raw",
        aliases=("b",),
        usage="back raw [N]",
        summary="Rewind by one raw TM transition.",
        details=(
            "You can pass N, as in `b 10` or `back raw 10`, to rewind multiple raw transitions.",
        ),
    ),
    CommandSpec(
        name="back routine",
        aliases=("br",),
        usage="back routine [N]",
        summary="Rewind to the previous lowering routine boundary.",
        details=(),
    ),
    CommandSpec(
        name="back instruction",
        aliases=("bi",),
        usage="back instruction [N]",
        summary="Rewind to the previous Meta-ASM instruction boundary.",
        details=(),
    ),
    CommandSpec(
        name="back block",
        aliases=("bb",),
        usage="back block [N]",
        summary="Rewind to the previous Meta-ASM block boundary.",
        details=(),
    ),
    CommandSpec(
        name="back source",
        aliases=("bs",),
        usage="back source [N]",
        summary="Rewind to the previous simulated source-TM transition.",
        details=(),
    ),
    CommandSpec(
        name="set max-raw",
        aliases=(),
        usage="set max-raw N",
        summary="Set the grouped-step raw transition guard.",
        details=(
            "Grouped stepping stops early with `max_raw` if it consumes more than this many raw transitions before reaching its boundary.",
        ),
    ),
    CommandSpec(
        name="help",
        aliases=("h", "?"),
        usage="help [topic]",
        summary="Show command help.",
        details=(
            "Use `help step raw`, `help where`, `help set`, or any alias such as `help s`.",
        ),
    ),
    CommandSpec(
        name="quit",
        aliases=("q",),
        usage="quit",
        summary="Exit debugger.",
        details=(),
    ),
)


FIELD_DOCS: tuple[tuple[str, str], ...] = (
    ("raw", "Absolute raw transition index in debugger history"),
    ("head", "Raw tape head position"),
    ("read", "Symbol currently under the raw tape head"),
    ("state", "Current raw TM control state"),
    ("block", "Meta-ASM block label"),
    ("instr", "Meta-ASM instruction index within the current block (`setup` before the first instruction)"),
    ("routine", "Lowering routine derived from that Meta-ASM instruction"),
    ("op", "Lowering sub-operation index within the routine"),
    ("move", "Raw TM head movement: L, R, or S"),
    ("next", "Next raw TM state after the row executes"),
)


TOPIC_ALIASES = {
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
    "set": "set max-raw",
    "set max-raw": "set max-raw",
    "help": "help",
    "h": "help",
    "?": "help",
    "quit": "quit",
    "q": "quit",
}


OUTPUT_LEGEND = (
    ("RAW", "raw=<step>  head=<raw tape head>  read='<symbol>'  state=<raw TM state>"),
    ("SOURCE", "block=<block>  instr=<instruction index>  routine=<lowering routine>  op=<sub-step>"),
    ("INSTRUCTION", "OPCODE <ARGS>"),
    ("NEXT ROW", "state=<row state>  read='<symbol>'  write='<symbol>'  move=<L|R|S>  next=<next raw state>"),
    ("LAST ROW", "Previously executed raw TM transition row (view only)"),
)


def canonical_topic(topic: str) -> str | None:
    """Normalize a help topic or alias to its canonical command name."""

    normalized = " ".join(topic.strip().split())
    if not normalized:
        return "help"
    return TOPIC_ALIASES.get(normalized)


def command_spec(name: str) -> CommandSpec | None:
    """Return the command specification for a canonical command name."""

    for spec in COMMAND_SPECS:
        if spec.name == name:
            return spec
    return None


__all__ = [
    "COMMAND_SPECS",
    "FIELD_DOCS",
    "OUTPUT_LEGEND",
    "CommandSpec",
    "canonical_topic",
    "command_spec",
]
