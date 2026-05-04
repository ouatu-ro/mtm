"""First raw-TM lowerings for small Meta-ASM instructions."""

from __future__ import annotations

from .meta_asm import BranchCmp, FindFirstRule, FindHeadCell, FindNextRule, Goto, Halt, Instruction, Seek, SeekOneOf, WriteGlobal
from .outer_tape import CELL, CMP_FLAG, END_RULES, HEAD, NO_HEAD, RULE, RULES
from .raw_tm import R, S, TMBuilder


def lower_seek(builder: TMBuilder, state: str, *, markers: set[str], direction: str, continuation_label: str) -> None:
    move = R if direction == "R" else -1
    continuation = builder.label_state(continuation_label)
    for symbol in builder.alphabet:
        if symbol in markers:
            builder.emit(state, symbol, continuation, symbol, S)
        else:
            builder.emit(state, symbol, state, symbol, move)


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
        case WriteGlobal(global_marker, literal_bits):
            bit_states = [builder.fresh(f"write_global_bit_{index}") for index in range(len(literal_bits))]
            builder.emit(state, global_marker, bit_states[0] if bit_states else builder.label_state(continuation_label), global_marker, R if bit_states else S)
            for index, bit in enumerate(literal_bits):
                next_state = bit_states[index + 1] if index + 1 < len(bit_states) else builder.label_state(continuation_label)
                for read_bit in ("0", "1"):
                    builder.emit(bit_states[index], read_bit, next_state, bit, R if index + 1 < len(bit_states) else S)
        case _:
            raise NotImplementedError(f"lowering not implemented for {instruction!r}")


__all__ = ["lower_instruction"]
