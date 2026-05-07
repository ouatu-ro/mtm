"""Meta-ASM host interpreter over sparse runtime tapes split into encoded UTM band tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .utm_band_layout import BLANK_SYMBOL, CELL, CMP_FLAG, END_CELL, END_FIELD, END_RULE, END_RULES, END_TAPE, HEAD, NO_HEAD, RULE, RULES, TAPE_LEFT, materialize_runtime_tape, split_runtime_tape
from .meta_asm import BranchAt, BranchCmp, CompareGlobalGlobal, CompareGlobalLiteral, CompareGlobalLocal, CopyGlobalGlobal, CopyGlobalToHeadSymbol, CopyHeadSymbolTo, CopyLocalGlobal, FindFirstRule, FindHeadCell, FindNextRule, Goto, Halt, MoveSimHeadLeft, MoveSimHeadRight, Program, Seek, SeekOneOf, Unimplemented, WriteGlobal, format_instruction
from .pretty import table

Side = Literal["left", "right"]


def left_index(left_band: list[str], address: int) -> int:
    return address + len(left_band)


def token_at(left_band: list[str], right_band: list[str], address: int) -> str:
    return right_band[address] if address >= 0 else left_band[left_index(left_band, address)]


@dataclass(frozen=True)
class DelimitedRegion:
    side: Side
    start: int
    end: int
    terminator: str
    label: str


def _tokens_for_region(left_band: list[str], right_band: list[str], region: DelimitedRegion) -> list[str]:
    return left_band if region.side == "left" else right_band


def _region_token(left_band: list[str], right_band: list[str], region: DelimitedRegion, offset: int) -> str:
    tokens = _tokens_for_region(left_band, right_band, region)
    index = region.start + offset
    if index > region.end:
        raise ValueError(f"offset {offset} crosses terminator for {region.label}")
    return tokens[index]


def _write_region_token(left_band: list[str], right_band: list[str], region: DelimitedRegion, offset: int, token: str) -> tuple[list[str], list[str]]:
    if region.start + offset >= region.end:
        raise ValueError(f"cannot write through terminator for {region.label}")
    if region.side == "left":
        left_band = list(left_band)
        left_band[region.start + offset] = token
        return left_band, right_band
    right_band = list(right_band)
    right_band[region.start + offset] = token
    return left_band, right_band


def _compare_delimited_regions(left_band: list[str], right_band: list[str], left_region: DelimitedRegion, right_region: DelimitedRegion, width: int) -> bool:
    for offset in range(width + 1):
        left_token = _region_token(left_band, right_band, left_region, offset)
        right_token = _region_token(left_band, right_band, right_region, offset)
        left_done = left_token == left_region.terminator
        right_done = right_token == right_region.terminator
        if left_done or right_done:
            return left_done and right_done
        if left_token != right_token:
            return False
    return False


def _copy_delimited_region(left_band: list[str], right_band: list[str], src_region: DelimitedRegion, dst_region: DelimitedRegion, width: int) -> tuple[list[str], list[str]]:
    for offset in range(width + 1):
        src_token = _region_token(left_band, right_band, src_region, offset)
        dst_token = _region_token(left_band, right_band, dst_region, offset)
        src_done = src_token == src_region.terminator
        dst_done = dst_token == dst_region.terminator
        if src_done or dst_done:
            if src_done and dst_done:
                return left_band, right_band
            raise ValueError(f"terminator mismatch while copying {src_region.label} to {dst_region.label}")
        left_band, right_band = _write_region_token(left_band, right_band, dst_region, offset, src_token)
    raise ValueError(f"missing terminator within width {width} while copying {src_region.label} to {dst_region.label}")


def global_field_region(left_band: list[str], marker: str) -> DelimitedRegion:
    start = left_band.index(marker) + 1
    end = left_band.index(END_FIELD, start)
    return DelimitedRegion("left", start, end, END_FIELD, marker)


def field_slice(left_band: list[str], marker: str) -> slice:
    region = global_field_region(left_band, marker)
    return slice(region.start, region.end)


def get_global_bits(left_band: list[str], marker: str) -> tuple[str, ...]:
    return tuple(left_band[field_slice(left_band, marker)])


def set_global_bits(left_band: list[str], marker: str, bits: tuple[str, ...]) -> list[str]:
    span = field_slice(left_band, marker)
    if len(bits) != span.stop - span.start:
        raise ValueError(f"wrong width for {marker}: expected {span.stop - span.start}, got {len(bits)}")
    left_band = list(left_band)
    left_band[span] = list(bits)
    return left_band


def runtime_address(left_band: list[str], side: Side, index: int) -> int:
    return index if side == "right" else index - len(left_band)


def band_position(left_band: list[str], right_band: list[str], address: int) -> tuple[Side, int]:
    if address >= 0:
        return "right", address
    return "left", left_index(left_band, address)


def simulated_left_cell_indices(left_band: list[str]) -> list[int]:
    tape_left = left_band.index(TAPE_LEFT)
    return [index for index, token in enumerate(left_band[:tape_left]) if token == CELL]


def simulated_right_cell_indices(right_band: list[str]) -> list[int]:
    return [index for index, token in enumerate(right_band) if token == CELL]


def find_head_cell(left_band: list[str], right_band: list[str]) -> int:
    tape_left = left_band.index(TAPE_LEFT)
    for index, token in enumerate(left_band[:tape_left]):
        if token == CELL and left_band[index + 1] == HEAD:
            return runtime_address(left_band, "left", index)
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
        raise ValueError("current instruction requires the runtime head to be on a rule marker")
    index = left_index(left_band, head_address)
    if left_band[index] != RULE:
        raise ValueError(f"expected current rule marker, got {left_band[index]!r}")
    return index


def local_field_slice(left_band: list[str], rule_index: int, marker: str) -> slice:
    return slice(*local_field_bounds(left_band, rule_index, marker))


def local_field_bounds(left_band: list[str], rule_index: int, marker: str) -> tuple[int, int]:
    rule_end = left_band.index(END_RULE, rule_index + 1)
    index = rule_index + 1
    while index < rule_end:
        if left_band[index] == marker:
            end = left_band.index(END_FIELD, index + 1)
            if end > rule_end:
                raise ValueError(f"field {marker} crosses rule boundary")
            return index + 1, end
        index += 1
    raise ValueError(f"missing local field {marker}")


def local_field_region(left_band: list[str], rule_index: int, marker: str) -> DelimitedRegion:
    start, end = local_field_bounds(left_band, rule_index, marker)
    return DelimitedRegion("left", start, end, END_FIELD, marker)


def find_next_rule(left_band: list[str], head_address: int | None) -> int:
    start = current_rule_index(left_band, head_address) + 1
    for index in range(start, len(left_band)):
        if left_band[index] in {RULE, END_RULES}:
            return index
    raise ValueError("unterminated rule registry")


def is_simulated_cell(left_band: list[str], right_band: list[str], head_address: int | None) -> bool:
    if head_address is None:
        return False
    side, index = band_position(left_band, right_band, head_address)
    tokens = right_band if side == "right" else left_band
    return 0 <= index < len(tokens) and tokens[index] == CELL


def head_symbol_region(left_band: list[str], right_band: list[str], head_address: int) -> DelimitedRegion:
    side, index = band_position(left_band, right_band, head_address)
    tokens = right_band if side == "right" else left_band
    start = index + 2
    end = tokens.index(END_CELL, start)
    return DelimitedRegion(side, start, end, END_CELL, "head symbol")


def blank_cell(left_band: list[str], head_marker: str) -> list[str]:
    return [CELL, head_marker, *get_global_bits(left_band, BLANK_SYMBOL), END_CELL]


def move_simulated_head(encoding, left_band: list[str], right_band: list[str], head_address: int, direction: int) -> tuple[list[str], list[str], int]:
    left_band = list(left_band)
    right_band = list(right_band)

    if direction == 0:
        return left_band, right_band, head_address

    side, old_index = band_position(left_band, right_band, head_address)
    if side == "left":
        left_cells = simulated_left_cell_indices(left_band)
        cell_position = left_cells.index(old_index)
        left_band[old_index + 1] = NO_HEAD

        if direction > 0:
            if cell_position + 1 < len(left_cells):
                next_index = left_cells[cell_position + 1]
                left_band[next_index + 1] = HEAD
                return left_band, right_band, runtime_address(left_band, "left", next_index)

            right_cells = simulated_right_cell_indices(right_band)
            if not right_cells:
                end_tape = right_band.index(END_TAPE)
                right_band[end_tape:end_tape] = blank_cell(left_band, NO_HEAD)
                right_cells = simulated_right_cell_indices(right_band)
            next_index = right_cells[0]
            right_band[next_index + 1] = HEAD
            return left_band, right_band, next_index

        if cell_position == 0:
            insert_at = 1
            left_band[insert_at:insert_at] = blank_cell(left_band, HEAD)
            return left_band, right_band, runtime_address(left_band, "left", insert_at)

        next_index = left_cells[cell_position - 1]
        left_band[next_index + 1] = HEAD
        return left_band, right_band, runtime_address(left_band, "left", next_index)

    right_cells = simulated_right_cell_indices(right_band)
    cell_position = right_cells.index(old_index)
    right_band[old_index + 1] = NO_HEAD

    if direction > 0:
        if cell_position + 1 < len(right_cells):
            next_index = right_cells[cell_position + 1]
        else:
            end_tape = right_band.index(END_TAPE)
            right_band[end_tape:end_tape] = blank_cell(left_band, HEAD)
            next_index = end_tape
        right_band[next_index + 1] = HEAD
        return left_band, right_band, next_index

    if cell_position > 0:
        next_index = right_cells[cell_position - 1]
        right_band[next_index + 1] = HEAD
        return left_band, right_band, next_index

    left_cells = simulated_left_cell_indices(left_band)
    if left_cells:
        next_index = left_cells[-1]
        left_band[next_index + 1] = HEAD
        return left_band, right_band, runtime_address(left_band, "left", next_index)

    insert_at = left_band.index(TAPE_LEFT)
    left_band[insert_at:insert_at] = blank_cell(left_band, HEAD)
    return left_band, right_band, runtime_address(left_band, "left", insert_at)


def seek_address(left_band: list[str], right_band: list[str], start: int | None, markers: set[str], direction: str) -> int:
    if start is None:
        raise ValueError("SEEK requires the runtime head to be positioned")
    lowest, highest = -len(left_band), len(right_band) - 1
    step = -1 if direction == "L" else 1
    address = start
    while lowest <= address <= highest:
        if token_at(left_band, right_band, address) in markers:
            return address
        address += step
    raise ValueError(f"failed to seek one of {sorted(markers)} in direction {direction}")


def head_value(left_band: list[str], right_band: list[str], head_address: int | None) -> str:
    if head_address is None:
        return "-"
    return token_at(left_band, right_band, head_address)


def format_meta_trace(trace: list[dict[str, object]]) -> str:
    rows = [[item["step"], item["label"], item["instruction"], item["head"], item["value"], item["outcome"]] for item in trace]
    return table(["step", "label", "instruction", "head", "value", "outcome"], rows)


def _run_meta_asm(program: Program, encoding, runtime_tape: dict[int, str], *, max_steps: int, start_label: str, stop_on_block_exit: bool):
    blocks = {block.label: block for block in program.blocks}
    label, instruction_index, head_address, status, reason = start_label, 0, None, "running", None
    trace: list[dict[str, object]] = []
    left_band, right_band = split_runtime_tape(runtime_tape)

    for step in range(max_steps):
        if status != "running":
            break

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
                instruction_index += 1
                outcome = f"{CMP_FLAG}={cmp_bit}"
            case CompareGlobalGlobal(src_marker, dst_marker, width):
                src_region = global_field_region(left_band, src_marker)
                dst_region = global_field_region(left_band, dst_marker)
                cmp_bit = "1" if _compare_delimited_regions(left_band, right_band, src_region, dst_region, width) else "0"
                left_band = set_global_bits(left_band, CMP_FLAG, (cmp_bit,))
                instruction_index += 1
                outcome = f"{CMP_FLAG}={cmp_bit}"
            case CompareGlobalLocal(global_marker, local_marker, width):
                rule_index = current_rule_index(left_band, head_address)
                global_region = global_field_region(left_band, global_marker)
                local_region = local_field_region(left_band, rule_index, local_marker)
                cmp_bit = "1" if _compare_delimited_regions(left_band, right_band, global_region, local_region, width) else "0"
                left_band = set_global_bits(left_band, CMP_FLAG, (cmp_bit,))
                instruction_index += 1
                outcome = f"{CMP_FLAG}={cmp_bit}"
            case BranchCmp(label_equal, label_not_equal):
                target = label_equal if get_global_bits(left_band, CMP_FLAG) == ("1",) else label_not_equal
                label, instruction_index = target, 0
                outcome = f"goto {target}"
            case BranchAt(marker, label_true, label_false):
                if head_address is None:
                    raise ValueError("BRANCH_AT requires the runtime head to be positioned")
                target = label_true if token_at(left_band, right_band, head_address) == marker else label_false
                label, instruction_index = target, 0
                outcome = f"goto {target}"
            case FindHeadCell():
                head_address = find_head_cell(left_band, right_band)
                instruction_index += 1
                outcome = f"head at {head_address}"
            case CopyHeadSymbolTo(global_marker, width):
                if not is_simulated_cell(left_band, right_band, head_address):
                    raise ValueError("COPY_HEAD_SYMBOL_TO requires the runtime head to be at a simulated #CELL")
                left_band, right_band = _copy_delimited_region(
                    left_band,
                    right_band,
                    head_symbol_region(left_band, right_band, head_address),
                    global_field_region(left_band, global_marker),
                    width,
                )
                instruction_index += 1
                outcome = f"{global_marker}<-head_symbol"
            case CopyGlobalToHeadSymbol(global_marker, width):
                if not is_simulated_cell(left_band, right_band, head_address):
                    raise ValueError("COPY_GLOBAL_TO_HEAD_SYMBOL requires the runtime head to be at a simulated #CELL")
                left_band, right_band = _copy_delimited_region(
                    left_band,
                    right_band,
                    global_field_region(left_band, global_marker),
                    head_symbol_region(left_band, right_band, head_address),
                    width,
                )
                instruction_index += 1
                outcome = f"head_symbol<-{global_marker}"
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
            case CopyLocalGlobal(local_marker, global_marker, width):
                rule_index = current_rule_index(left_band, head_address)
                left_band, right_band = _copy_delimited_region(
                    left_band,
                    right_band,
                    local_field_region(left_band, rule_index, local_marker),
                    global_field_region(left_band, global_marker),
                    width,
                )
                instruction_index += 1
                outcome = f"{global_marker}<-{local_marker}"
            case CopyGlobalGlobal(src_marker, dst_marker, width):
                left_band, right_band = _copy_delimited_region(
                    left_band,
                    right_band,
                    global_field_region(left_band, src_marker),
                    global_field_region(left_band, dst_marker),
                    width,
                )
                instruction_index += 1
                outcome = f"{dst_marker}<-{src_marker}"
            case WriteGlobal(global_marker, literal_bits):
                left_band = set_global_bits(left_band, global_marker, literal_bits)
                instruction_index += 1
                outcome = f"{global_marker}={''.join(literal_bits)}"
            case MoveSimHeadLeft(_symbol_width):
                if not is_simulated_cell(left_band, right_band, head_address):
                    raise ValueError("MOVE_SIM_HEAD_LEFT requires the runtime head to be at a simulated #CELL")
                left_band, right_band, head_address = move_simulated_head(encoding, left_band, right_band, head_address, -1)
                instruction_index += 1
                outcome = f"head at {head_address}"
            case MoveSimHeadRight(_symbol_width):
                if not is_simulated_cell(left_band, right_band, head_address):
                    raise ValueError("MOVE_SIM_HEAD_RIGHT requires the runtime head to be at a simulated #CELL")
                left_band, right_band, head_address = move_simulated_head(encoding, left_band, right_band, head_address, 1)
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

        trace.append({
            "step": step,
            "label": block.label,
            "instruction": format_instruction(instruction),
            "head": "-" if head_address is None else head_address,
            "value": head_value(left_band, right_band, head_address),
            "outcome": outcome,
        })

        if stop_on_block_exit and status == "running" and label != block.label:
            reason = "block exited"
            break

    if status == "running":
        status, reason = "halted", "fuel exhausted" if reason is None else reason
    runtime_tape = materialize_runtime_tape(left_band, right_band)
    return {
        "status": status,
        "runtime_tape": runtime_tape,
        "trace": trace,
        "reason": reason,
        "label": label,
        "instruction_index": instruction_index,
        "head_address": head_address,
    }


def run_meta_asm_block_runtime(program: Program, encoding, runtime_tape: dict[int, str], *, label: str, max_steps: int = 100):
    return _run_meta_asm(program, encoding, runtime_tape, max_steps=max_steps, start_label=label, stop_on_block_exit=True)


def run_meta_asm_runtime(program: Program, encoding, runtime_tape: dict[int, str], *, max_steps: int = 100):
    result = _run_meta_asm(program, encoding, runtime_tape, max_steps=max_steps, start_label=program.entry_label, stop_on_block_exit=False)
    return result["status"], result["runtime_tape"], result["trace"], result["reason"]


__all__ = ["format_meta_trace", "run_meta_asm_block_runtime", "run_meta_asm_runtime"]
