"""Build the future Meta-ASM interpreter rules."""

from __future__ import annotations

from dataclasses import dataclass

from .meta_asm import BranchCmp, CompareGlobalLiteral, CopyHeadSymbolTo, FindFirstRule, FindHeadCell, Goto, Halt, Program, Unimplemented, format_instruction
from .outer_tape import CELL, CMP_FLAG, END_FIELD, END_RULES, HEAD, RULE, RULES, TMProgram, place_on_negative_side, place_on_positive_side, split_outer_tape
from .pretty import table

@dataclass(frozen=True)
class MetaInterpreterRules:
    """Raw TM rules for the interpreter side of the system."""

    tm_program: TMProgram; start_state: str = "U_START"; halt_state: str = "U_HALT"


def rebuild_outer_tape(left_band: list[str], right_band: list[str]) -> dict[int, str]:
    outer_tape = {}
    outer_tape.update(place_on_negative_side(left_band, start=-1))
    outer_tape.update(place_on_positive_side(right_band, start=0))
    return outer_tape


def field_slice(left_band: list[str], marker: str) -> slice:
    start = left_band.index(marker) + 1
    end = left_band.index(END_FIELD, start)
    return slice(start, end)


def get_global_bits(left_band: list[str], marker: str) -> tuple[str, ...]:
    return tuple(left_band[field_slice(left_band, marker)])


def set_global_bits(left_band: list[str], marker: str, bits: tuple[str, ...]) -> list[str]:
    span = field_slice(left_band, marker)
    if len(bits) != span.stop - span.start:
        raise ValueError(f"wrong width for {marker}: expected {span.stop - span.start}, got {len(bits)}")
    left_band = list(left_band)
    left_band[span] = list(bits)
    return left_band


def find_head_cell(right_band: list[str]) -> int:
    for index, token in enumerate(right_band):
        if token == CELL and right_band[index + 1] == HEAD:
            return index
    raise ValueError("no simulated head cell found")


def find_first_rule(left_band: list[str]) -> int:
    start = left_band.index(RULES) + 1
    for index in range(start, len(left_band)):
        if left_band[index] in {RULE, END_RULES}:
            return index
    raise ValueError("rule section is malformed")


def head_value(left_band: list[str], right_band: list[str], head_address: int | None) -> str:
    if head_address is None:
        return "-"
    return right_band[head_address] if head_address >= 0 else left_band[head_address + len(left_band)]


def format_meta_trace(trace: list[dict[str, object]]) -> str:
    rows = [[item["step"], item["label"], item["instruction"], item["head"], item["value"], item["outcome"]] for item in trace]
    return table(["step", "label", "instruction", "head", "value", "outcome"], rows)


def run_meta_asm_host(program: Program, outer_tape: dict[int, str], *, max_steps: int = 100):
    blocks = {block.label: block for block in program.blocks}
    label, instruction_index, head_address, status, reason = program.entry_label, 0, None, "running", None
    trace: list[dict[str, object]] = []
    outer_tape = dict(outer_tape)

    for step in range(max_steps):
        if status != "running":
            break

        left_band, right_band = split_outer_tape(outer_tape)
        block = blocks[label]
        if instruction_index >= len(block.instructions):
            status, reason = "halted", f"fell off end of block {label}"
            break

        instruction = block.instructions[instruction_index]
        outcome = ""

        match instruction:
            case CompareGlobalLiteral(global_marker, literal_bits):
                cmp_bit = "1" if get_global_bits(left_band, global_marker) == literal_bits else "0"
                left_band = set_global_bits(left_band, CMP_FLAG, (cmp_bit,))
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{CMP_FLAG}={cmp_bit}"
            case BranchCmp(label_equal, label_not_equal):
                target = label_equal if get_global_bits(left_band, CMP_FLAG) == ("1",) else label_not_equal
                label, instruction_index = target, 0
                outcome = f"goto {target}"
            case FindHeadCell():
                head_address = find_head_cell(right_band)
                instruction_index += 1
                outcome = f"head at {head_address}"
            case CopyHeadSymbolTo(global_marker, width):
                if head_address is None or head_address < 0 or right_band[head_address] != CELL:
                    raise ValueError("COPY_HEAD_SYMBOL_TO requires the outer head to be at a simulated #CELL")
                symbol_bits = tuple(right_band[head_address + 2:head_address + 2 + width])
                left_band = set_global_bits(left_band, global_marker, symbol_bits)
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{global_marker}={''.join(symbol_bits)}"
            case FindFirstRule():
                rule_index = find_first_rule(left_band)
                head_address = rule_index - len(left_band)
                instruction_index += 1
                outcome = f"head at {left_band[rule_index]}"
            case Goto(target):
                label, instruction_index = target, 0
                outcome = f"goto {target}"
            case Halt():
                status, reason = "halted", "HALT"
                outcome = "halt"
            case Unimplemented(note):
                status, reason = "halted", f"UNIMPLEMENTED ASM instruction: {note}"
                outcome = "unimplemented"
            case _:
                status, reason = "halted", f"ASM instruction not yet supported by host runner: {format_instruction(instruction)}"
                outcome = "unsupported"

        left_band, right_band = split_outer_tape(outer_tape)
        trace.append({
            "step": step,
            "label": block.label,
            "instruction": format_instruction(instruction),
            "head": "-" if head_address is None else head_address,
            "value": head_value(left_band, right_band, head_address),
            "outcome": outcome,
        })

    if status == "running":
        status, reason = "halted", "fuel exhausted"
    return status, outer_tape, trace, reason


def build_meta_interpreter_rules(encoding) -> MetaInterpreterRules:
    raise NotImplementedError(f"Next step: generate interpreter rules for {encoding!r}.")
