"""Lower individual Meta-ASM instructions into Routine IR.

Each function in this module corresponds to the meaning of a Meta-ASM
instruction or a small piece of the rule-matching protocol. The functions build
Routine objects only; they do not emit raw TM transitions and they do not touch
TMBuilder.
"""

from __future__ import annotations

from ..meta_asm import BranchAt, BranchCmp, CompareGlobalLiteral, CompareGlobalLocal, CopyGlobalGlobal, CopyGlobalToHeadSymbol, CopyHeadSymbolTo, CopyLocalGlobal, FindFirstRule, FindHeadCell, FindNextRule, Goto, Halt, Instruction, MoveSimHeadLeft, MoveSimHeadRight, Seek, SeekOneOf, WriteGlobal
from ..utm_band_layout import CELL, CMP_FLAG, CUR_STATE, CUR_SYMBOL, END_RULES, END_TAPE, END_TAPE_LEFT, END_CELL, HEAD, MOVE_DIR, NEXT_STATE, NO_HEAD, REGS, RULE, RULES, RUNTIME_BLANK, TAPE, TAPE_LEFT, WRITE_SYMBOL
from .combinators import branch_bit_at_offset, emit_expected_bit_branch, move_steps, seek, seek_until_one_of, seek_then_write_bit_at_offset, write_bit_at_offset, write_current_bit
from .constants import ACTIVE_RULE, L, Label, R, S, global_direction
from .contracts import HeadAt, HeadAtOneOf, HeadOnRuntimeTape
from .ops import EmitAllOp, EmitAnyExceptOp, EmitOp, BranchAtOp
from .routines import Routine, RoutineDraft


def _seek_active_rule(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    """Seek back to the rule currently marked as active."""

    seek(draft, source, markers={ACTIVE_RULE}, direction="R", target=target)


def _activate_rule_at_head(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    """Mark the rule under the head as the active rule."""

    draft.add(EmitOp(source, RULE, target, ACTIVE_RULE, S))
    draft.add(EmitOp(source, ACTIVE_RULE, target, ACTIVE_RULE, S))


def _write_cmp_flag(draft: RoutineDraft, source: Label, *, bit: str, target: Label) -> None:
    """Write a comparison result bit into the comparison flag register."""

    write_state = draft.local("write_cmp_flag")
    draft.add(EmitOp(source, CMP_FLAG, write_state, CMP_FLAG, R))
    write_current_bit(draft, write_state, bit=bit, target=target, move=L)


def _encoded_blank(symbol_width: int) -> tuple[str, ...]:
    """Encoded blank bits; source encoding reserves all-zero bits for blank."""

    return ("0",) * symbol_width


def _jump_from_right_tape_to_left_tape(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    """Cross the registry/rule block from ``#TAPE`` to ``#TAPE_LEFT``."""

    seek(draft, source, markers={TAPE_LEFT}, direction="L", target=target)


def _jump_from_left_tape_to_right_tape(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    """Cross the registry/rule block from ``#TAPE_LEFT`` to ``#TAPE``."""

    seek(draft, source, markers={TAPE}, direction="R", target=target)


def _seek_regs_from_anywhere(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    """Seek the register block from either side of the split source tape."""

    seek_right = draft.local("seek_regs_right")
    seek_until_one_of(draft, source, found={REGS}, boundary={END_TAPE_LEFT}, direction="L", on_found=target, on_boundary=seek_right)
    seek(draft, seek_right, markers={REGS}, direction="R", target=target)


def _seek_global_from_simulated_cell(draft: RoutineDraft, source: Label, *, marker: str, target: Label) -> None:
    """Seek a global register from either simulated tape side."""

    seek_right = draft.local("seek_global_right")
    seek_until_one_of(draft, source, found={marker}, boundary={END_TAPE_LEFT}, direction="L", on_found=target, on_boundary=seek_right)
    seek(draft, seek_right, markers={marker}, direction="R", target=target)


def _seek_head_from_global_area(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    """Seek the simulated head from the register/rule area on either side."""

    seek_right = draft.local("seek_head_right")
    seek_until_one_of(draft, source, found={HEAD}, boundary={END_TAPE_LEFT}, direction="L", on_found=target, on_boundary=seek_right)
    seek(draft, seek_right, markers={HEAD}, direction="R", target=target)


def _construct_blank_right_cell(draft: RoutineDraft, source: Label, *, target: Label, encoded_blank: tuple[str, ...]) -> None:
    """Overwrite ``#END_TAPE`` with a new blank headed cell and a new end marker."""

    write_head = draft.local("extend_right_head")
    symbol_width = len(encoded_blank)
    bit_states = [draft.local(f"extend_right_bit_{index}") for index in range(symbol_width)]
    end_cell = draft.local("extend_right_end_cell")
    end_tape = draft.local("extend_right_end_tape")
    rewind = draft.local("extend_right_rewind")
    draft.add(EmitOp(source, END_TAPE, write_head, CELL, R))
    draft.add(EmitOp(write_head, RUNTIME_BLANK, bit_states[0] if bit_states else end_cell, HEAD, R))
    for index, bit in enumerate(encoded_blank):
        next_state = bit_states[index + 1] if index + 1 < symbol_width else end_cell
        draft.add(EmitOp(bit_states[index], RUNTIME_BLANK, next_state, bit, R))
    draft.add(EmitOp(end_cell, RUNTIME_BLANK, end_tape, END_CELL, R))
    draft.add(EmitOp(end_tape, RUNTIME_BLANK, rewind, END_TAPE, L))
    move_steps(draft, rewind, steps=symbol_width + 2, direction="L", target=target)


def _construct_blank_left_cell(draft: RoutineDraft, source: Label, *, target: Label, encoded_blank: tuple[str, ...]) -> None:
    """Move ``#END_TAPE_LEFT`` left and write a blank headed cell after it."""

    bit_states = [draft.local(f"extend_left_bit_{index}") for index in range(len(encoded_blank))]
    write_head = draft.local("extend_left_head")
    write_cell = draft.local("extend_left_cell")
    write_boundary = draft.local("extend_left_boundary")
    first_target = bit_states[0] if bit_states else write_head
    draft.add(EmitOp(source, END_TAPE_LEFT, first_target, END_CELL, L))
    for index, bit in enumerate(reversed(encoded_blank)):
        next_state = bit_states[index + 1] if index + 1 < len(bit_states) else write_head
        draft.add(EmitOp(bit_states[index], RUNTIME_BLANK, next_state, bit, L))
    draft.add(EmitOp(write_head, RUNTIME_BLANK, write_cell, HEAD, L))
    draft.add(EmitOp(write_cell, RUNTIME_BLANK, write_boundary, CELL, L))
    draft.add(EmitOp(write_boundary, RUNTIME_BLANK, target, END_TAPE_LEFT, R))


def _halt_routine(state: Label, cont: Label) -> Routine:
    del cont
    draft = RoutineDraft("halt", entry=state, exits=("__HALT__",), falls_through=False)
    draft.add(EmitAllOp(state, "__HALT__", S))
    return draft.build()


def _goto_routine(state: Label, cont: Label, label: Label) -> Routine:
    del cont
    draft = RoutineDraft("goto", entry=state, exits=(label,), falls_through=False)
    draft.add(EmitAllOp(state, label, S))
    return draft.build()


def _seek_routine(state: Label, cont: Label, marker: str, direction: str) -> Routine:
    draft = RoutineDraft("seek", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAt(marker))
    seek(draft, state, markers={marker}, direction=direction, target=cont)
    return draft.build()


def _seek_one_of_routine(state: Label, cont: Label, markers: tuple[str, ...], direction: str) -> Routine:
    draft = RoutineDraft("seek_one_of", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAtOneOf(markers))
    seek(draft, state, markers=set(markers), direction=direction, target=cont)
    return draft.build()


def _find_first_rule_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("find_first_rule", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAtOneOf((RULE, END_RULES)))
    seek_regs = draft.local("seek_regs")
    seek_rules = draft.local("seek_rules")
    seek_rule = draft.local("seek_rule")
    mark_rule = draft.local("mark_rule")
    draft.add(EmitAllOp(state, seek_regs, S))
    _seek_regs_from_anywhere(draft, seek_regs, target=seek_rules)
    seek(draft, seek_rules, markers={RULES}, direction="R", target=seek_rule)
    seek(draft, seek_rule, markers={RULE, END_RULES}, direction="R", target=mark_rule)
    draft.add(EmitOp(mark_rule, RULE, cont, ACTIVE_RULE, S))
    draft.add(EmitOp(mark_rule, END_RULES, cont, END_RULES, S))
    return draft.build()


def _find_next_rule_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("find_next_rule", entry=state, exits=(cont,), requires=HeadAtOneOf((RULE, ACTIVE_RULE)), ensures=HeadAtOneOf((RULE, END_RULES)))
    seek_next = draft.local("seek_next")
    mark_rule = draft.local("mark_rule")
    draft.add(EmitOp(state, ACTIVE_RULE, seek_next, RULE, R))
    draft.add(EmitOp(state, RULE, seek_next, RULE, R))
    seek(draft, seek_next, markers={RULE, END_RULES}, direction="R", target=mark_rule)
    draft.add(EmitOp(mark_rule, RULE, cont, ACTIVE_RULE, S))
    draft.add(EmitOp(mark_rule, END_RULES, cont, END_RULES, S))
    return draft.build()


def _find_head_cell_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("find_head_cell", entry=state, exits=(cont, "STUCK"), requires=HeadOnRuntimeTape(), ensures=HeadAt(CELL))
    scan_right = draft.local("scan_right")
    right_cell = draft.local("right_cell")
    right_flag = draft.local("right_flag")
    right_return = draft.local("right_return")
    seek_right_origin = draft.local("seek_right_origin")
    seek_left_origin = draft.local("seek_left_origin")
    scan_left = draft.local("scan_left")
    left_cell = draft.local("left_cell")
    left_flag = draft.local("left_flag")
    left_leave_cell = draft.local("left_leave_cell")
    left_return = draft.local("left_return")
    draft.add(EmitAllOp(state, scan_right, S))
    seek_until_one_of(draft, scan_right, found={CELL}, boundary={END_TAPE}, direction="R", on_found=right_cell, on_boundary=seek_right_origin)
    draft.add(EmitOp(right_cell, CELL, right_flag, CELL, R))
    draft.add(EmitOp(right_flag, HEAD, right_return, HEAD, L))
    draft.add(EmitAnyExceptOp(right_flag, HEAD, scan_right, R))
    draft.add(EmitOp(right_return, CELL, cont, CELL, S))
    seek(draft, seek_right_origin, markers={TAPE}, direction="L", target=seek_left_origin)
    _jump_from_right_tape_to_left_tape(draft, seek_left_origin, target=scan_left)
    seek_until_one_of(draft, scan_left, found={CELL}, boundary={END_TAPE_LEFT}, direction="L", on_found=left_cell, on_boundary="STUCK")
    draft.add(EmitOp(left_cell, CELL, left_flag, CELL, R))
    draft.add(EmitOp(left_flag, HEAD, left_return, HEAD, L))
    draft.add(EmitAnyExceptOp(left_flag, HEAD, left_leave_cell, L))
    draft.add(EmitOp(left_leave_cell, CELL, scan_left, CELL, L))
    draft.add(EmitOp(left_return, CELL, cont, CELL, S))
    return draft.build()


def _move_sim_head_right_routine(state: Label, cont: Label, symbol_width: int) -> Routine:
    draft = RoutineDraft("move_sim_head_right", entry=state, exits=(cont, "STUCK"), requires=HeadAt(CELL), ensures=HeadAt(CELL))
    clear_flag = draft.local("clear_flag")
    scan_next = draft.local("scan_next")
    next_cell = draft.local("next_cell")
    mark_head = draft.local("mark_head")
    inspect_next = draft.local("inspect_next")
    jump_right = draft.local("jump_right")
    scan_right = draft.local("scan_right")
    extend_right = draft.local("extend_right")
    draft.add(EmitOp(state, CELL, clear_flag, CELL, R))
    draft.add(EmitOp(clear_flag, HEAD, scan_next, NO_HEAD, R))
    draft.add(EmitOp(clear_flag, NO_HEAD, scan_next, NO_HEAD, R))
    seek(draft, scan_next, markers={CELL, TAPE_LEFT, END_TAPE}, direction="R", target=inspect_next)
    draft.add(EmitOp(inspect_next, CELL, next_cell, CELL, S))
    draft.add(EmitOp(inspect_next, TAPE_LEFT, jump_right, TAPE_LEFT, S))
    draft.add(EmitOp(inspect_next, END_TAPE, extend_right, END_TAPE, S))
    _jump_from_left_tape_to_right_tape(draft, jump_right, target=scan_right)
    seek_until_one_of(draft, scan_right, found={CELL}, boundary={END_TAPE}, direction="R", on_found=next_cell, on_boundary=extend_right)
    _construct_blank_right_cell(draft, extend_right, target=next_cell, encoded_blank=_encoded_blank(symbol_width))
    draft.add(EmitOp(next_cell, CELL, mark_head, CELL, R))
    draft.add(EmitOp(mark_head, HEAD, cont, HEAD, L))
    draft.add(EmitOp(mark_head, NO_HEAD, cont, HEAD, L))
    return draft.build()


def _move_sim_head_left_routine(state: Label, cont: Label, symbol_width: int) -> Routine:
    draft = RoutineDraft("move_sim_head_left", entry=state, exits=(cont, "STUCK"), requires=HeadAt(CELL), ensures=HeadAt(CELL))
    clear_flag = draft.local("clear_flag")
    leave_current = draft.local("leave_current")
    scan_prev = draft.local("scan_prev")
    prev_cell = draft.local("prev_cell")
    mark_head = draft.local("mark_head")
    inspect_prev = draft.local("inspect_prev")
    jump_left = draft.local("jump_left")
    scan_left = draft.local("scan_left")
    extend_left = draft.local("extend_left")
    draft.add(EmitOp(state, CELL, clear_flag, CELL, R))
    draft.add(EmitOp(clear_flag, HEAD, leave_current, NO_HEAD, L))
    draft.add(EmitOp(clear_flag, NO_HEAD, leave_current, NO_HEAD, L))
    draft.add(EmitOp(leave_current, CELL, scan_prev, CELL, L))
    seek(draft, scan_prev, markers={CELL, TAPE, END_TAPE_LEFT}, direction="L", target=inspect_prev)
    draft.add(EmitOp(inspect_prev, CELL, prev_cell, CELL, S))
    draft.add(EmitOp(inspect_prev, TAPE, jump_left, TAPE, S))
    draft.add(EmitOp(inspect_prev, END_TAPE_LEFT, extend_left, END_TAPE_LEFT, S))
    _jump_from_right_tape_to_left_tape(draft, jump_left, target=scan_left)
    seek(draft, scan_left, markers={CELL, END_TAPE_LEFT}, direction="L", target=inspect_prev)
    _construct_blank_left_cell(draft, extend_left, target=prev_cell, encoded_blank=_encoded_blank(symbol_width))
    draft.add(EmitOp(prev_cell, CELL, mark_head, CELL, R))
    draft.add(EmitOp(mark_head, HEAD, cont, HEAD, L))
    draft.add(EmitOp(mark_head, NO_HEAD, cont, HEAD, L))
    return draft.build()


def deactivate_active_rule_routine(state: Label, cont: Label) -> Routine:
    """Return the active rule marker to a normal rule marker."""

    draft = RoutineDraft("deactivate_active_rule", entry=state, exits=(cont,), requires=HeadAtOneOf((ACTIVE_RULE, RULE)), ensures=HeadAt(RULE))
    draft.add(EmitOp(state, ACTIVE_RULE, cont, RULE, S))
    draft.add(EmitOp(state, RULE, cont, RULE, S))
    return draft.build()


def _copy_global_global_routine(state: Label, cont: Label, src_marker: str, dst_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_global_global", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadOnRuntimeTape())
    to_dst, to_src = global_direction(src_marker, dst_marker), global_direction(dst_marker, src_marker)
    current = draft.local("seek_src")
    seek_regs = draft.local("seek_regs")
    _seek_regs_from_anywhere(draft, state, target=seek_regs)
    seek(draft, seek_regs, markers={src_marker}, direction="R", target=current)
    for index in range(width):
        branches = branch_bit_at_offset(draft, current, offset=index + 1, move_after_read=R if to_dst == "R" else L, prefix="src", index=index)
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            if index + 1 == width:
                seek_then_write_bit_at_offset(draft, branch.state, marker=dst_marker, seek_direction=to_dst, bit=branch.bit, offset=index + 1, target=cont, write_move=S, prefix="dst", index=index)
            else:
                back_to_src = draft.local(f"back_to_src_{branch.bit}_{index}")
                seek_then_write_bit_at_offset(draft, branch.state, marker=dst_marker, seek_direction=to_dst, bit=branch.bit, offset=index + 1, target=back_to_src, write_move=R if to_src == "R" else L, prefix="dst", index=index)
                seek(draft, back_to_src, markers={src_marker}, direction=to_src, target=next_iter)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _copy_local_global_routine(state: Label, cont: Label, local_marker: str, global_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_local_global", entry=state, exits=(cont,), requires=HeadAtOneOf((RULE, ACTIVE_RULE)), ensures=HeadAt(ACTIVE_RULE))
    activate_rule = draft.local("activate_rule")
    current = activate_rule
    _activate_rule_at_head(draft, state, target=activate_rule)
    for index in range(width):
        local_marker_state = draft.local(f"local_marker_{index}")
        seek(draft, current, markers={local_marker}, direction="R", target=local_marker_state)
        branches = branch_bit_at_offset(draft, local_marker_state, offset=index + 1, move_after_read=L, prefix="local", index=index)
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            back_to_rule = draft.local(f"back_to_rule_{branch.bit}_{index}")
            seek_then_write_bit_at_offset(draft, branch.state, marker=global_marker, seek_direction="L", bit=branch.bit, offset=index + 1, target=back_to_rule, write_move=S, prefix="global", index=index)
            _seek_active_rule(draft, back_to_rule, target=cont if index + 1 == width else next_iter)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _copy_head_symbol_to_routine(state: Label, cont: Label, global_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_head_symbol_to", entry=state, exits=(cont,), requires=HeadAt(CELL), ensures=HeadOnRuntimeTape())
    current = state
    for index in range(width):
        branches = branch_bit_at_offset(draft, current, offset=index + 2, move_after_read=L, prefix="head", index=index)
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            global_marker_state = draft.local(f"global_marker_{branch.bit}_{index}")
            _seek_global_from_simulated_cell(draft, branch.state, marker=global_marker, target=global_marker_state)
            if index + 1 == width:
                write_bit_at_offset(draft, global_marker_state, bit=branch.bit, offset=index + 1, target=cont, write_move=S, prefix="global", index=index)
            else:
                back_to_head = draft.local(f"back_to_head_{branch.bit}_{index}")
                back_to_cell = draft.local(f"back_to_cell_{branch.bit}_{index}")
                write_bit_at_offset(draft, global_marker_state, bit=branch.bit, offset=index + 1, target=back_to_head, write_move=S, prefix="global", index=index)
                _seek_head_from_global_area(draft, back_to_head, target=back_to_cell)
                draft.add(EmitOp(back_to_cell, HEAD, next_iter, HEAD, L))
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _copy_global_to_head_symbol_routine(state: Label, cont: Label, global_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_global_to_head_symbol", entry=state, exits=(cont,), requires=HeadAt(CELL), ensures=HeadOnRuntimeTape())
    current = state
    for index in range(width):
        global_marker_state = draft.local(f"global_marker_{index}")
        _seek_global_from_simulated_cell(draft, current, marker=global_marker, target=global_marker_state)
        branches = branch_bit_at_offset(draft, global_marker_state, offset=index + 1, move_after_read=R, prefix="global", index=index)
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            head_flag_state = draft.local(f"head_flag_{branch.bit}_{index}")
            cell_state = draft.local(f"cell_state_{branch.bit}_{index}")
            _seek_head_from_global_area(draft, branch.state, target=head_flag_state)
            draft.add(EmitOp(head_flag_state, HEAD, cell_state, HEAD, L))
            if index + 1 == width:
                write_bit_at_offset(draft, cell_state, bit=branch.bit, offset=index + 2, target=cont, write_move=S, prefix="head", index=index)
            else:
                back_to_cell = draft.local(f"back_to_cell_{branch.bit}_{index}")
                write_bit_at_offset(draft, cell_state, bit=branch.bit, offset=index + 2, target=back_to_cell, write_move=L, prefix="head", index=index)
                seek(draft, back_to_cell, markers={CELL}, direction="L", target=next_iter)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _compare_global_literal_routine(state: Label, cont: Label, global_marker: str, literal_bits: tuple[str, ...]) -> Routine:
    draft = RoutineDraft("compare_global_literal", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAt(CMP_FLAG))
    dir_to_cmp = global_direction(global_marker, CMP_FLAG)
    seek_regs = draft.local("seek_regs")
    marker_state = draft.local("marker")
    current = draft.local("read_0")
    _seek_regs_from_anywhere(draft, state, target=seek_regs)
    seek(draft, seek_regs, markers={global_marker}, direction="R", target=marker_state)
    draft.add(EmitOp(marker_state, global_marker, current, global_marker, R))
    for index, expected in enumerate(literal_bits):
        next_read = draft.local(f"read_{index + 1}") if index + 1 < len(literal_bits) else None
        seek_false = draft.local(f"seek_false_{index}")
        seek_true = draft.local(f"seek_true_{index}") if next_read is None else None
        expected_target = next_read if next_read else seek_true
        expected_move = R if next_read else (R if dir_to_cmp == "R" else L)
        mismatch_move = R if dir_to_cmp == "R" else L
        emit_expected_bit_branch(draft, current, expected=expected, match_target=expected_target, mismatch_target=seek_false, match_move=expected_move, mismatch_move=mismatch_move)
        cmp_false_state = draft.local(f"false_cmp_{index}")
        seek(draft, seek_false, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_false_state)
        if seek_true is not None:
            cmp_true_state = draft.local(f"true_cmp_{index}")
            seek(draft, seek_true, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_true_state)
            _write_cmp_flag(draft, cmp_true_state, bit="1", target=cont)
        _write_cmp_flag(draft, cmp_false_state, bit="0", target=cont)
        current = next_read if next_read else current
    return draft.build()


def _compare_global_local_routine(state: Label, cont: Label, global_marker: str, local_marker: str, width: int) -> Routine:
    draft = RoutineDraft("compare_global_local", entry=state, exits=(cont,), requires=HeadAtOneOf((RULE, ACTIVE_RULE)), ensures=HeadAt(ACTIVE_RULE))
    dir_to_cmp = global_direction(global_marker, CMP_FLAG)
    activate_rule = draft.local("activate_rule")
    current = activate_rule
    _activate_rule_at_head(draft, state, target=activate_rule)
    for index in range(width):
        local_marker_state = draft.local(f"local_marker_{index}")
        seek(draft, current, markers={local_marker}, direction="R", target=local_marker_state)
        branches = branch_bit_at_offset(draft, local_marker_state, offset=index + 1, move_after_read=L, prefix="local", index=index)
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            global_marker_state = draft.local(f"global_marker_{branch.bit}_{index}")
            seek(draft, branch.state, markers={global_marker}, direction="L", target=global_marker_state)
            global_read = draft.local(f"global_read_{branch.bit}_{index}")
            move_steps(draft, global_marker_state, steps=index + 1, direction="R", target=global_read)
            mismatch_bit = "1" if branch.bit == "0" else "0"
            mismatch_seek = draft.local(f"mismatch_seek_{branch.bit}_{index}")
            draft.add(EmitOp(global_read, mismatch_bit, mismatch_seek, mismatch_bit, S))
            cmp_false_state = draft.local(f"false_cmp_{branch.bit}_{index}")
            after_false = draft.local(f"after_false_{branch.bit}_{index}")
            seek(draft, mismatch_seek, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_false_state)
            _write_cmp_flag(draft, cmp_false_state, bit="0", target=after_false)
            _seek_active_rule(draft, after_false, target=cont)
            if next_iter is not None:
                back_to_rule = draft.local(f"back_to_rule_{branch.bit}_{index}")
                draft.add(EmitOp(global_read, branch.bit, back_to_rule, branch.bit, S))
                _seek_active_rule(draft, back_to_rule, target=next_iter)
            else:
                match_seek = draft.local(f"match_seek_{branch.bit}_{index}")
                cmp_true_state = draft.local(f"true_cmp_{branch.bit}_{index}")
                after_true = draft.local(f"after_true_{branch.bit}_{index}")
                draft.add(EmitOp(global_read, branch.bit, match_seek, branch.bit, S))
                seek(draft, match_seek, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_true_state)
                _write_cmp_flag(draft, cmp_true_state, bit="1", target=after_true)
                _seek_active_rule(draft, after_true, target=cont)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _branch_cmp_routine(state: Label, cont: Label, label_equal: Label, label_not_equal: Label) -> Routine:
    del cont
    draft = RoutineDraft(
        "branch_cmp",
        entry=state,
        exits=(label_equal, label_not_equal),
        falls_through=False,
        requires=HeadAtOneOf((CMP_FLAG, ACTIVE_RULE)),
        ensures=HeadOnRuntimeTape(),
    )
    active_seek_cmp = draft.local("active_seek_cmp")
    active_read_cmp = draft.local("active_read_cmp")
    active_bit = draft.local("active_bit")
    active_seek_eq = draft.local("active_seek_eq")
    active_seek_neq = draft.local("active_seek_neq")
    draft.add(EmitOp(state, ACTIVE_RULE, active_seek_cmp, ACTIVE_RULE, L))
    seek(draft, active_seek_cmp, markers={CMP_FLAG}, direction="L", target=active_read_cmp)
    draft.add(EmitOp(active_read_cmp, CMP_FLAG, active_bit, CMP_FLAG, R))
    draft.add(EmitOp(active_bit, "1", active_seek_eq, "1", L))
    draft.add(EmitOp(active_bit, "0", active_seek_neq, "0", L))
    seek(draft, active_seek_eq, markers={ACTIVE_RULE}, direction="R", target=label_equal)
    seek(draft, active_seek_neq, markers={ACTIVE_RULE}, direction="R", target=label_not_equal)
    read_cmp = draft.local("read")
    draft.add(EmitOp(state, CMP_FLAG, read_cmp, CMP_FLAG, R))
    draft.add(EmitOp(read_cmp, "1", label_equal, "1", S))
    draft.add(EmitOp(read_cmp, "0", label_not_equal, "0", S))
    return draft.build()


def _write_global_routine(state: Label, cont: Label, global_marker: str, literal_bits: tuple[str, ...]) -> Routine:
    draft = RoutineDraft("write_global", entry=state, exits=(cont,), requires=HeadAt(global_marker), ensures=HeadOnRuntimeTape())
    bit_states = [draft.local(f"bit_{index}") for index in range(len(literal_bits))]
    draft.add(EmitOp(state, global_marker, bit_states[0] if bit_states else cont, global_marker, R if bit_states else S))
    for index, bit in enumerate(literal_bits):
        next_state = bit_states[index + 1] if index + 1 < len(bit_states) else cont
        write_current_bit(draft, bit_states[index], bit=bit, target=next_state, move=R if index + 1 < len(bit_states) else S)
    return draft.build()


def lower_instruction_to_routine(instruction: Instruction, *, state: Label, cont: Label) -> Routine:
    """Lower one Meta-ASM instruction into one Routine."""

    match instruction:
        case Halt():
            return _halt_routine(state, cont)
        case Goto(label):
            return _goto_routine(state, cont, label)
        case Seek(marker, direction):
            return _seek_routine(state, cont, marker, direction)
        case SeekOneOf(markers, direction):
            return _seek_one_of_routine(state, cont, markers, direction)
        case FindFirstRule():
            return _find_first_rule_routine(state, cont)
        case FindNextRule():
            return _find_next_rule_routine(state, cont)
        case FindHeadCell():
            return _find_head_cell_routine(state, cont)
        case BranchAt(marker, label_true, label_false):
            del cont
            draft = RoutineDraft(
                "branch_at",
                entry=state,
                exits=(label_true, label_false),
                falls_through=False,
                requires=HeadOnRuntimeTape(),
                ensures=HeadOnRuntimeTape(),
            )
            draft.add(BranchAtOp(state, marker, label_true, label_false))
            return draft.build()
        case BranchCmp(label_equal, label_not_equal):
            return _branch_cmp_routine(state, cont, label_equal, label_not_equal)
        case CompareGlobalLiteral(global_marker, literal_bits):
            return _compare_global_literal_routine(state, cont, global_marker, literal_bits)
        case CompareGlobalLocal(global_marker, local_marker, width):
            return _compare_global_local_routine(state, cont, global_marker, local_marker, width)
        case CopyGlobalGlobal(src_marker, dst_marker, width):
            return _copy_global_global_routine(state, cont, src_marker, dst_marker, width)
        case CopyLocalGlobal(local_marker, global_marker, width):
            return _copy_local_global_routine(state, cont, local_marker, global_marker, width)
        case CopyHeadSymbolTo(global_marker, width):
            return _copy_head_symbol_to_routine(state, cont, global_marker, width)
        case CopyGlobalToHeadSymbol(global_marker, width):
            return _copy_global_to_head_symbol_routine(state, cont, global_marker, width)
        case WriteGlobal(global_marker, literal_bits):
            return _write_global_routine(state, cont, global_marker, literal_bits)
        case MoveSimHeadLeft(symbol_width):
            return _move_sim_head_left_routine(state, cont, symbol_width)
        case MoveSimHeadRight(symbol_width):
            return _move_sim_head_right_routine(state, cont, symbol_width)
        case _:
            raise NotImplementedError(f"lowering not implemented for {instruction!r}")


__all__ = ["deactivate_active_rule_routine", "lower_instruction_to_routine"]
