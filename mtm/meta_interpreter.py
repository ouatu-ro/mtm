"""Build the future Meta-ASM interpreter rules."""

from __future__ import annotations

from dataclasses import dataclass

from .meta_asm import (
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
    Program,
    Seek,
    SeekOneOf,
    Unimplemented,
    WriteGlobal,
    format_instruction,
)
from .outer_tape import CELL, CMP_FLAG, END_FIELD, END_RULE, END_RULES, END_TAPE, HEAD, NO_HEAD, RULE, RULES, TAPE, TMProgram, encode_symbol, place_on_negative_side, place_on_positive_side, split_outer_tape
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


def left_index(left_band: list[str], address: int) -> int:
    return address + len(left_band)


def token_at(left_band: list[str], right_band: list[str], address: int) -> str:
    return right_band[address] if address >= 0 else left_band[left_index(left_band, address)]


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


def current_rule_index(left_band: list[str], head_address: int | None) -> int:
    if head_address is None or head_address >= 0:
        raise ValueError("current instruction requires the outer head to be on a rule marker")
    index = left_index(left_band, head_address)
    if left_band[index] != RULE:
        raise ValueError(f"expected current rule marker, got {left_band[index]!r}")
    return index


def local_field_slice(left_band: list[str], rule_index: int, marker: str) -> slice:
    rule_end = left_band.index(END_RULE, rule_index + 1)
    index = rule_index + 1
    while index < rule_end:
        if left_band[index] == marker:
            end = left_band.index(END_FIELD, index + 1)
            if end > rule_end:
                raise ValueError(f"field {marker} crosses rule boundary")
            return slice(index + 1, end)
        index += 1
    raise ValueError(f"missing local field {marker}")


def get_local_bits(left_band: list[str], rule_index: int, marker: str) -> tuple[str, ...]:
    return tuple(left_band[local_field_slice(left_band, rule_index, marker)])


def find_next_rule(left_band: list[str], head_address: int | None) -> int:
    start = current_rule_index(left_band, head_address) + 1
    for index in range(start, len(left_band)):
        if left_band[index] in {RULE, END_RULES}:
            return index
    raise ValueError("unterminated rule registry")


def cell_span(symbol_width: int) -> int:
    return 3 + symbol_width


def read_head_symbol_bits(right_band: list[str], head_address: int, width: int) -> tuple[str, ...]:
    return tuple(right_band[head_address + 2:head_address + 2 + width])


def write_head_symbol_bits(right_band: list[str], head_address: int, bits: tuple[str, ...]) -> list[str]:
    right_band = list(right_band)
    right_band[head_address + 2:head_address + 2 + len(bits)] = list(bits)
    return right_band


def move_simulated_head(encoding, right_band: list[str], head_address: int, direction: int) -> tuple[list[str], int]:
    span, blank_bits = cell_span(encoding.symbol_width), encode_symbol(encoding, encoding.blank)
    right_band = list(right_band)
    old_head = head_address

    if direction > 0:
        next_head = old_head + span
        if right_band[next_head] == END_TAPE:
            right_band = right_band[:-1] + [CELL, NO_HEAD, *blank_bits, END_CELL, END_TAPE]
        right_band[old_head + 1], right_band[next_head + 1] = NO_HEAD, HEAD
        return right_band, next_head

    if direction < 0:
        if old_head == 1:
            right_band = [TAPE, CELL, NO_HEAD, *blank_bits, END_CELL, *right_band[1:]]
            old_head += span
            next_head = 1
        else:
            next_head = old_head - span
        right_band[old_head + 1], right_band[next_head + 1] = NO_HEAD, HEAD
        return right_band, next_head

    return right_band, old_head


def all_addresses(left_band: list[str], right_band: list[str]) -> list[int]:
    return list(range(-len(left_band), 0)) + list(range(len(right_band)))


def seek_address(left_band: list[str], right_band: list[str], start: int | None, markers: set[str], direction: str) -> int:
    addresses = all_addresses(left_band, right_band)
    if start is None:
        raise ValueError("SEEK requires the outer head to be positioned")
    start_index = addresses.index(start)
    step = -1 if direction == "L" else 1
    index = start_index
    while 0 <= index < len(addresses):
        address = addresses[index]
        if token_at(left_band, right_band, address) in markers:
            return address
        index += step
    raise ValueError(f"failed to seek one of {sorted(markers)} in direction {direction}")


def head_value(left_band: list[str], right_band: list[str], head_address: int | None) -> str:
    if head_address is None:
        return "-"
    return token_at(left_band, right_band, head_address)


def format_meta_trace(trace: list[dict[str, object]]) -> str:
    rows = [[item["step"], item["label"], item["instruction"], item["head"], item["value"], item["outcome"]] for item in trace]
    return table(["step", "label", "instruction", "head", "value", "outcome"], rows)


def run_meta_asm_host(program: Program, encoding, outer_tape: dict[int, str], *, max_steps: int = 100):
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
            case Seek(marker, direction):
                head_address = seek_address(left_band, right_band, head_address, {marker}, direction)
                instruction_index += 1
                outcome = f"head at {marker}"
            case SeekOneOf(markers, direction):
                head_address = seek_address(left_band, right_band, head_address, set(markers), direction)
                instruction_index += 1
                outcome = f"head at {token_at(left_band, right_band, head_address)}"
            case CompareGlobalLiteral(global_marker, literal_bits):
                cmp_bit = "1" if get_global_bits(left_band, global_marker) == literal_bits else "0"
                left_band = set_global_bits(left_band, CMP_FLAG, (cmp_bit,))
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{CMP_FLAG}={cmp_bit}"
            case CompareGlobalLocal(global_marker, local_marker, _width):
                rule_index = current_rule_index(left_band, head_address)
                cmp_bit = "1" if get_global_bits(left_band, global_marker) == get_local_bits(left_band, rule_index, local_marker) else "0"
                left_band = set_global_bits(left_band, CMP_FLAG, (cmp_bit,))
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{CMP_FLAG}={cmp_bit}"
            case BranchCmp(label_equal, label_not_equal):
                target = label_equal if get_global_bits(left_band, CMP_FLAG) == ("1",) else label_not_equal
                label, instruction_index = target, 0
                outcome = f"goto {target}"
            case BranchAt(marker, label_true, label_false):
                if head_address is None:
                    raise ValueError("BRANCH_AT requires the outer head to be positioned")
                target = label_true if token_at(left_band, right_band, head_address) == marker else label_false
                label, instruction_index = target, 0
                outcome = f"goto {target}"
            case FindHeadCell():
                head_address = find_head_cell(right_band)
                instruction_index += 1
                outcome = f"head at {head_address}"
            case CopyHeadSymbolTo(global_marker, width):
                if head_address is None or head_address < 0 or right_band[head_address] != CELL:
                    raise ValueError("COPY_HEAD_SYMBOL_TO requires the outer head to be at a simulated #CELL")
                symbol_bits = read_head_symbol_bits(right_band, head_address, width)
                left_band = set_global_bits(left_band, global_marker, symbol_bits)
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{global_marker}={''.join(symbol_bits)}"
            case CopyGlobalToHeadSymbol(global_marker, width):
                if head_address is None or head_address < 0 or right_band[head_address] != CELL:
                    raise ValueError("COPY_GLOBAL_TO_HEAD_SYMBOL requires the outer head to be at a simulated #CELL")
                symbol_bits = get_global_bits(left_band, global_marker)
                if len(symbol_bits) != width:
                    raise ValueError(f"wrong width for {global_marker}: expected {width}, got {len(symbol_bits)}")
                right_band = write_head_symbol_bits(right_band, head_address, symbol_bits)
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"head_symbol={''.join(symbol_bits)}"
            case FindFirstRule():
                rule_index = find_first_rule(left_band)
                head_address = rule_index - len(left_band)
                instruction_index += 1
                outcome = f"head at {left_band[rule_index]}"
            case FindNextRule():
                rule_index = find_next_rule(left_band, head_address)
                head_address = rule_index - len(left_band)
                instruction_index += 1
                outcome = f"head at {left_band[rule_index]}"
            case CopyLocalGlobal(local_marker, global_marker, _width):
                rule_index = current_rule_index(left_band, head_address)
                left_band = set_global_bits(left_band, global_marker, get_local_bits(left_band, rule_index, local_marker))
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{global_marker}<-{local_marker}"
            case CopyGlobalGlobal(src_marker, dst_marker, _width):
                left_band = set_global_bits(left_band, dst_marker, get_global_bits(left_band, src_marker))
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{dst_marker}<-{src_marker}"
            case WriteGlobal(global_marker, literal_bits):
                left_band = set_global_bits(left_band, global_marker, literal_bits)
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"{global_marker}={''.join(literal_bits)}"
            case MoveSimHeadLeft():
                if head_address is None or head_address < 0 or right_band[head_address] != CELL:
                    raise ValueError("MOVE_SIM_HEAD_LEFT requires the outer head to be at a simulated #CELL")
                right_band, head_address = move_simulated_head(encoding, right_band, head_address, -1)
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"head at {head_address}"
            case MoveSimHeadRight():
                if head_address is None or head_address < 0 or right_band[head_address] != CELL:
                    raise ValueError("MOVE_SIM_HEAD_RIGHT requires the outer head to be at a simulated #CELL")
                right_band, head_address = move_simulated_head(encoding, right_band, head_address, 1)
                outer_tape = rebuild_outer_tape(left_band, right_band)
                instruction_index += 1
                outcome = f"head at {head_address}"
            case Goto(target):
                label, instruction_index = target, 0
                outcome = f"goto {target}"
            case Halt():
                status, reason = "halted", "HALT" if block.label == "HALT" else f"HALT at {block.label}"
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
