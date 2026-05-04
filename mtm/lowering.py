"""First raw-TM lowerings for small Meta-ASM instructions."""

from __future__ import annotations

from .meta_asm import (
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
    Instruction,
    Seek,
    SeekOneOf,
    WriteGlobal,
)
from .outer_tape import CELL, CMP_FLAG, CUR_STATE, CUR_SYMBOL, END_RULES, HEAD, MOVE_DIR, NEXT_STATE, RULE, RULES, TMP, WRITE_SYMBOL
from .raw_tm import L, R, S, TMBuilder

GLOBAL_MARKERS = (CUR_STATE, CUR_SYMBOL, WRITE_SYMBOL, NEXT_STATE, MOVE_DIR, CMP_FLAG, TMP)


def lower_seek(builder: TMBuilder, state: str, *, markers: set[str], direction: str, continuation_label: str) -> None:
    move = R if direction == "R" else L
    continuation = builder.label_state(continuation_label)
    for symbol in builder.alphabet:
        if symbol in markers:
            builder.emit(state, symbol, continuation, symbol, S)
        else:
            builder.emit(state, symbol, state, symbol, move)


def global_direction(src_marker: str, dst_marker: str) -> str:
    return "R" if GLOBAL_MARKERS.index(src_marker) < GLOBAL_MARKERS.index(dst_marker) else "L"


def move_steps(builder: TMBuilder, state: str, *, steps: int, direction: str, continuation_label: str) -> None:
    if steps == 0:
        builder.emit_all(state, builder.label_state(continuation_label), move=S)
        return
    move = R if direction == "R" else L
    current = state
    for index in range(steps):
        next_state = builder.label_state(continuation_label) if index + 1 == steps else builder.fresh(f"{state}_move_{index}")
        builder.emit_all(current, next_state, move=move)
        current = next_state


def branch_on_bit(builder: TMBuilder, state: str, *, zero_label: str, one_label: str, move: int) -> None:
    builder.emit(state, "0", builder.label_state(zero_label), "0", move)
    builder.emit(state, "1", builder.label_state(one_label), "1", move)


def write_current_bit(builder: TMBuilder, state: str, *, bit: str, continuation_label: str, move: int) -> None:
    next_state = builder.label_state(continuation_label)
    builder.emit(state, "0", next_state, bit, move)
    builder.emit(state, "1", next_state, bit, move)


def write_cmp_flag(builder: TMBuilder, state: str, *, bit: str, continuation_label: str) -> None:
    write_state = builder.fresh("write_cmp_flag")
    builder.emit(state, CMP_FLAG, write_state, CMP_FLAG, R)
    write_current_bit(builder, write_state, bit=bit, continuation_label=continuation_label, move=L)


def lower_copy_global_global(builder: TMBuilder, state: str, *, src_marker: str, dst_marker: str, width: int, continuation_label: str) -> None:
    to_dst, to_src = global_direction(src_marker, dst_marker), global_direction(dst_marker, src_marker)
    current = state
    for index in range(width):
        src_read = builder.fresh(f"copy_gg_src_{index}")
        move_steps(builder, current, steps=index + 1, direction="R", continuation_label=src_read)
        bit0, bit1 = builder.fresh(f"copy_gg_bit0_{index}"), builder.fresh(f"copy_gg_bit1_{index}")
        branch_on_bit(builder, src_read, zero_label=bit0, one_label=bit1, move=R if to_dst == "R" else L)
        next_iter = builder.fresh(f"copy_gg_next_{index}") if index + 1 < width else None
        for bit_state, bit in ((bit0, "0"), (bit1, "1")):
            dst_marker_state = builder.fresh(f"copy_gg_dst_marker_{bit}_{index}")
            lower_seek(builder, bit_state, markers={dst_marker}, direction=to_dst, continuation_label=dst_marker_state)
            dst_write = builder.fresh(f"copy_gg_dst_write_{bit}_{index}")
            move_steps(builder, dst_marker_state, steps=index + 1, direction="R", continuation_label=dst_write)
            if index + 1 == width:
                write_current_bit(builder, dst_write, bit=bit, continuation_label=continuation_label, move=S)
            else:
                back_to_src = builder.fresh(f"copy_gg_back_to_src_{bit}_{index}")
                write_current_bit(builder, dst_write, bit=bit, continuation_label=back_to_src, move=R if to_src == "R" else L)
                lower_seek(builder, back_to_src, markers={src_marker}, direction=to_src, continuation_label=next_iter)
        if next_iter is not None:
            current = next_iter


def lower_copy_local_global(builder: TMBuilder, state: str, *, local_marker: str, global_marker: str, width: int, continuation_label: str) -> None:
    current = state
    for index in range(width):
        local_marker_state = builder.fresh(f"copy_lg_local_marker_{index}")
        lower_seek(builder, current, markers={local_marker}, direction="R", continuation_label=local_marker_state)
        local_read = builder.fresh(f"copy_lg_local_read_{index}")
        move_steps(builder, local_marker_state, steps=index + 1, direction="R", continuation_label=local_read)
        bit0, bit1 = builder.fresh(f"copy_lg_bit0_{index}"), builder.fresh(f"copy_lg_bit1_{index}")
        branch_on_bit(builder, local_read, zero_label=bit0, one_label=bit1, move=L)
        next_iter = builder.fresh(f"copy_lg_next_{index}") if index + 1 < width else None
        for bit_state, bit in ((bit0, "0"), (bit1, "1")):
            global_marker_state = builder.fresh(f"copy_lg_global_marker_{bit}_{index}")
            lower_seek(builder, bit_state, markers={global_marker}, direction="L", continuation_label=global_marker_state)
            global_write = builder.fresh(f"copy_lg_global_write_{bit}_{index}")
            move_steps(builder, global_marker_state, steps=index + 1, direction="R", continuation_label=global_write)
            if index + 1 == width:
                write_current_bit(builder, global_write, bit=bit, continuation_label=continuation_label, move=S)
            else:
                back_to_rule = builder.fresh(f"copy_lg_back_to_rule_{bit}_{index}")
                write_current_bit(builder, global_write, bit=bit, continuation_label=back_to_rule, move=R)
                lower_seek(builder, back_to_rule, markers={RULE}, direction="R", continuation_label=next_iter)
        if next_iter is not None:
            current = next_iter


def lower_copy_head_symbol_to(builder: TMBuilder, state: str, *, global_marker: str, width: int, continuation_label: str) -> None:
    current = state
    for index in range(width):
        head_read = builder.fresh(f"copy_hg_head_read_{index}")
        move_steps(builder, current, steps=index + 2, direction="R", continuation_label=head_read)
        bit0, bit1 = builder.fresh(f"copy_hg_bit0_{index}"), builder.fresh(f"copy_hg_bit1_{index}")
        branch_on_bit(builder, head_read, zero_label=bit0, one_label=bit1, move=L)
        next_iter = builder.fresh(f"copy_hg_next_{index}") if index + 1 < width else None
        for bit_state, bit in ((bit0, "0"), (bit1, "1")):
            global_marker_state = builder.fresh(f"copy_hg_global_marker_{bit}_{index}")
            lower_seek(builder, bit_state, markers={global_marker}, direction="L", continuation_label=global_marker_state)
            global_write = builder.fresh(f"copy_hg_global_write_{bit}_{index}")
            move_steps(builder, global_marker_state, steps=index + 1, direction="R", continuation_label=global_write)
            if index + 1 == width:
                write_current_bit(builder, global_write, bit=bit, continuation_label=continuation_label, move=S)
            else:
                back_to_cell = builder.fresh(f"copy_hg_back_to_cell_{bit}_{index}")
                write_current_bit(builder, global_write, bit=bit, continuation_label=back_to_cell, move=R)
                lower_seek(builder, back_to_cell, markers={CELL}, direction="R", continuation_label=next_iter)
        if next_iter is not None:
            current = next_iter


def lower_copy_global_to_head_symbol(builder: TMBuilder, state: str, *, global_marker: str, width: int, continuation_label: str) -> None:
    current = state
    for index in range(width):
        global_marker_state = builder.fresh(f"copy_gh_global_marker_{index}")
        lower_seek(builder, current, markers={global_marker}, direction="L", continuation_label=global_marker_state)
        global_read = builder.fresh(f"copy_gh_global_read_{index}")
        move_steps(builder, global_marker_state, steps=index + 1, direction="R", continuation_label=global_read)
        bit0, bit1 = builder.fresh(f"copy_gh_bit0_{index}"), builder.fresh(f"copy_gh_bit1_{index}")
        branch_on_bit(builder, global_read, zero_label=bit0, one_label=bit1, move=R)
        next_iter = builder.fresh(f"copy_gh_next_{index}") if index + 1 < width else None
        for bit_state, bit in ((bit0, "0"), (bit1, "1")):
            cell_state = builder.fresh(f"copy_gh_cell_state_{bit}_{index}")
            lower_seek(builder, bit_state, markers={CELL}, direction="R", continuation_label=cell_state)
            head_write = builder.fresh(f"copy_gh_head_write_{bit}_{index}")
            move_steps(builder, cell_state, steps=index + 2, direction="R", continuation_label=head_write)
            if index + 1 == width:
                write_current_bit(builder, head_write, bit=bit, continuation_label=continuation_label, move=S)
            else:
                back_to_cell = builder.fresh(f"copy_gh_back_to_cell_{bit}_{index}")
                write_current_bit(builder, head_write, bit=bit, continuation_label=back_to_cell, move=L)
                lower_seek(builder, back_to_cell, markers={CELL}, direction="L", continuation_label=next_iter)
        if next_iter is not None:
            current = next_iter


def lower_compare_global_literal(builder: TMBuilder, state: str, *, global_marker: str, literal_bits: tuple[str, ...], continuation_label: str) -> None:
    dir_to_cmp = global_direction(global_marker, CMP_FLAG)
    current = builder.fresh("cmp_glob_read_0")
    builder.emit(state, global_marker, current, global_marker, R)
    for index, expected in enumerate(literal_bits):
        next_read = builder.fresh(f"cmp_glob_read_{index + 1}") if index + 1 < len(literal_bits) else None
        seek_true = builder.fresh(f"cmp_glob_seek_true_{index}")
        seek_false = builder.fresh(f"cmp_glob_seek_false_{index}")
        if expected == "0":
            builder.emit(current, "0", next_read if next_read else seek_true, "0", R if next_read else (R if dir_to_cmp == "R" else L))
            builder.emit(current, "1", seek_false, "1", R if dir_to_cmp == "R" else L)
        else:
            builder.emit(current, "1", next_read if next_read else seek_true, "1", R if next_read else (R if dir_to_cmp == "R" else L))
            builder.emit(current, "0", seek_false, "0", R if dir_to_cmp == "R" else L)
        cmp_true_state = builder.fresh(f"cmp_glob_true_cmp_{index}")
        cmp_false_state = builder.fresh(f"cmp_glob_false_cmp_{index}")
        lower_seek(builder, seek_true, markers={CMP_FLAG}, direction=dir_to_cmp, continuation_label=cmp_true_state)
        lower_seek(builder, seek_false, markers={CMP_FLAG}, direction=dir_to_cmp, continuation_label=cmp_false_state)
        write_cmp_flag(builder, cmp_true_state, bit="1", continuation_label=continuation_label)
        write_cmp_flag(builder, cmp_false_state, bit="0", continuation_label=continuation_label)
        current = next_read if next_read else current


def lower_compare_global_local(builder: TMBuilder, state: str, *, global_marker: str, local_marker: str, width: int, continuation_label: str) -> None:
    dir_to_cmp = global_direction(global_marker, CMP_FLAG)
    current = state
    for index in range(width):
        local_marker_state = builder.fresh(f"cmp_gl_local_marker_{index}")
        lower_seek(builder, current, markers={local_marker}, direction="R", continuation_label=local_marker_state)
        local_read = builder.fresh(f"cmp_gl_local_read_{index}")
        move_steps(builder, local_marker_state, steps=index + 1, direction="R", continuation_label=local_read)
        next_iter = builder.fresh(f"cmp_gl_next_{index}") if index + 1 < width else None
        for local_bit in ("0", "1"):
            global_seek = builder.fresh(f"cmp_gl_seek_global_{local_bit}_{index}")
            builder.emit(local_read, local_bit, global_seek, local_bit, L)
            global_marker_state = builder.fresh(f"cmp_gl_global_marker_{local_bit}_{index}")
            lower_seek(builder, global_seek, markers={global_marker}, direction="L", continuation_label=global_marker_state)
            global_read = builder.fresh(f"cmp_gl_global_read_{local_bit}_{index}")
            move_steps(builder, global_marker_state, steps=index + 1, direction="R", continuation_label=global_read)
            mismatch_seek = builder.fresh(f"cmp_gl_mismatch_seek_{local_bit}_{index}")
            if next_iter is not None:
                back_to_rule = builder.fresh(f"cmp_gl_back_to_rule_{local_bit}_{index}")
                builder.emit(global_read, local_bit, back_to_rule, local_bit, R)
                lower_seek(builder, back_to_rule, markers={RULE}, direction="R", continuation_label=next_iter)
            else:
                match_seek = builder.fresh(f"cmp_gl_match_seek_{local_bit}_{index}")
                cmp_true_state = builder.fresh(f"cmp_gl_true_cmp_{local_bit}_{index}")
                builder.emit(global_read, local_bit, match_seek, local_bit, R if dir_to_cmp == "R" else L)
                lower_seek(builder, match_seek, markers={CMP_FLAG}, direction=dir_to_cmp, continuation_label=cmp_true_state)
                write_cmp_flag(builder, cmp_true_state, bit="1", continuation_label=continuation_label)
            builder.emit(global_read, "1" if local_bit == "0" else "0", mismatch_seek, "1" if local_bit == "0" else "0", R if dir_to_cmp == "R" else L)
            cmp_false_state = builder.fresh(f"cmp_gl_false_cmp_{local_bit}_{index}")
            lower_seek(builder, mismatch_seek, markers={CMP_FLAG}, direction=dir_to_cmp, continuation_label=cmp_false_state)
            write_cmp_flag(builder, cmp_false_state, bit="0", continuation_label=continuation_label)
        if next_iter is not None:
            current = next_iter


def lower_instruction(builder: TMBuilder, instruction: Instruction, *, state: str, continuation_label: str) -> None:
    """Lower one small Meta-ASM instruction into raw TM transitions.

    Current fragment contracts:
    - `HALT`: no precondition on head position.
    - `GOTO`: no precondition on head position.
    - `BRANCH_CMP`: head is on the `#CMP_FLAG` marker.
    - `WRITE_GLOBAL`: head is on the target global marker.
    - `SEEK` / `SEEK_ONE_OF`: head is somewhere on the outer tape.
    - `FIND_FIRST_RULE`: head is somewhere on the outer tape.
    - `FIND_NEXT_RULE`: head is on the current `#RULE`.
    - `FIND_HEAD_CELL`: head is somewhere on the outer tape.
    """

    match instruction:
        case Halt():
            builder.emit_all(state, builder.halt_state, move=S)
        case Goto(label):
            builder.emit_all(state, builder.label_state(label), move=S)
        case Seek(marker, direction):
            lower_seek(builder, state, markers={marker}, direction=direction, continuation_label=continuation_label)
        case SeekOneOf(markers, direction):
            lower_seek(builder, state, markers=set(markers), direction=direction, continuation_label=continuation_label)
        case FindFirstRule():
            seek_rules = builder.fresh("find_first_rule_seek_rules")
            seek_rule = builder.fresh("find_first_rule_seek_rule")
            lower_seek(builder, seek_rules, markers={RULES}, direction="L", continuation_label=seek_rule)
            lower_seek(builder, seek_rule, markers={RULE, END_RULES}, direction="R", continuation_label=continuation_label)
            builder.emit_all(state, seek_rules, move=S)
        case FindNextRule():
            seek_next = builder.fresh("find_next_rule_seek_next")
            builder.emit(state, RULE, seek_next, RULE, R)
            lower_seek(builder, seek_next, markers={RULE, END_RULES}, direction="R", continuation_label=continuation_label)
        case FindHeadCell():
            scan_cell = builder.fresh("find_head_cell_scan")
            inspect_flag = builder.fresh("find_head_cell_flag")
            return_cell = builder.fresh("find_head_cell_return")
            builder.emit_all(state, scan_cell, move=S)
            for symbol in builder.alphabet:
                if symbol == CELL:
                    builder.emit(scan_cell, symbol, inspect_flag, symbol, R)
                else:
                    builder.emit(scan_cell, symbol, scan_cell, symbol, R)
            builder.emit(inspect_flag, HEAD, return_cell, HEAD, -1)
            for symbol in builder.alphabet:
                if symbol != HEAD:
                    builder.emit(inspect_flag, symbol, scan_cell, symbol, R)
            builder.emit(return_cell, CELL, builder.label_state(continuation_label), CELL, S)
        case BranchCmp(label_equal, label_not_equal):
            read_cmp = builder.fresh("branch_cmp_read")
            builder.emit(state, CMP_FLAG, read_cmp, CMP_FLAG, R)
            builder.emit(read_cmp, "1", builder.label_state(label_equal), "1", S)
            builder.emit(read_cmp, "0", builder.label_state(label_not_equal), "0", S)
        case CompareGlobalLiteral(global_marker, literal_bits):
            lower_compare_global_literal(builder, state, global_marker=global_marker, literal_bits=literal_bits, continuation_label=continuation_label)
        case CompareGlobalLocal(global_marker, local_marker, width):
            lower_compare_global_local(builder, state, global_marker=global_marker, local_marker=local_marker, width=width, continuation_label=continuation_label)
        case CopyGlobalGlobal(src_marker, dst_marker, width):
            lower_copy_global_global(builder, state, src_marker=src_marker, dst_marker=dst_marker, width=width, continuation_label=continuation_label)
        case CopyLocalGlobal(local_marker, global_marker, width):
            lower_copy_local_global(builder, state, local_marker=local_marker, global_marker=global_marker, width=width, continuation_label=continuation_label)
        case CopyHeadSymbolTo(global_marker, width):
            lower_copy_head_symbol_to(builder, state, global_marker=global_marker, width=width, continuation_label=continuation_label)
        case CopyGlobalToHeadSymbol(global_marker, width):
            lower_copy_global_to_head_symbol(builder, state, global_marker=global_marker, width=width, continuation_label=continuation_label)
        case WriteGlobal(global_marker, literal_bits):
            bit_states = [builder.fresh(f"write_global_bit_{index}") for index in range(len(literal_bits))]
            builder.emit(state, global_marker, bit_states[0] if bit_states else builder.label_state(continuation_label), global_marker, R if bit_states else S)
            for index, bit in enumerate(literal_bits):
                next_state = bit_states[index + 1] if index + 1 < len(bit_states) else builder.label_state(continuation_label)
                for read_bit in ("0", "1"):
                    builder.emit(bit_states[index], read_bit, next_state, bit, R if index + 1 < len(bit_states) else S)
        case _:
            raise NotImplementedError(f"lowering not implemented for {instruction!r}")


def lower_instruction_sequence(
    builder: TMBuilder,
    instructions: tuple[Instruction, ...] | list[Instruction],
    *,
    start_state: str,
    exit_label: str,
) -> None:
    """Lower a small straight-line Meta-ASM instruction sequence.

    This helper is for block-level composition tests. It assumes any branching
    instruction appears as the last instruction in the sequence.
    """

    current_state = start_state
    instructions = tuple(instructions)
    for index, instruction in enumerate(instructions):
        continuation_label = exit_label if index + 1 == len(instructions) else builder.fresh(f"{start_state}_cont_{index}")
        lower_instruction(builder, instruction, state=current_state, continuation_label=continuation_label)
        current_state = continuation_label


__all__ = ["lower_instruction", "lower_instruction_sequence"]
