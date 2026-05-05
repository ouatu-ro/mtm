"""Turn Meta-ASM blocks into Routine sequences.

Meta-ASM blocks are still written as instruction lists with labels. This module
adds the block-level protocol around those instructions: where each block
expects the head to start, how instruction fallthrough labels are connected, and
the special cleanup step after a matched rule has been copied.
"""

from __future__ import annotations

from dataclasses import replace

from ..meta_asm import Block, Instruction, Program, Seek, SeekOneOf
from ..meta_asm import format_instruction
from ..utm_band_layout import CUR_STATE, END_RULES, MOVE_DIR
from .constants import ACTIVE_RULE, Label
from .instruction_lowering import deactivate_active_rule_routine, lower_instruction_to_routine
from .routines import NameSupply, Routine
from .source_map import OpSource, RoutineSource


def _attach_instruction_source(
    routine: Routine,
    *,
    block_label: str,
    instruction_index: int | None,
    instruction: Instruction | None,
    instruction_text: str | None = None,
) -> Routine:
    """Return ``routine`` annotated with block/instruction metadata."""

    text = instruction_text
    if text is None and instruction is not None:
        text = format_instruction(instruction)
    return replace(
        routine,
        source=RoutineSource(
            block_label=block_label,
            routine_name=routine.name,
            routine_index=None,
            instruction_index=instruction_index,
            instruction=instruction,
            instruction_text=text,
        ),
        op_sources=tuple(
            OpSource(
                routine_name=routine.name,
                routine_index=None,
                block_label=block_label,
                instruction_index=instruction_index,
                instruction=instruction,
                instruction_text=text,
                op_index=op_index,
                op=op,
            )
            for op_index, op in enumerate(routine.ops)
        ),
    )


def block_entry_setup(block: Block) -> Instruction | None:
    """Return the synthetic seek needed before a block's real instructions.

    The generated UTM program enters different blocks from different head
    positions. These setup instructions normalize the head position so each
    block body can be lowered with simpler assumptions.
    """

    if block.label == "START_STEP":
        return Seek(CUR_STATE, "L")
    if block.label == "LOOKUP_RULE":
        return SeekOneOf((ACTIVE_RULE, END_RULES), "R")
    if block.label in {"CHECK_STATE", "CHECK_READ", "NEXT_RULE", "MATCHED_RULE"}:
        return Seek(ACTIVE_RULE, "R")
    if block.label in {"DISPATCH_MOVE", "CHECK_RIGHT"}:
        return Seek(MOVE_DIR, "L")
    return None


def instruction_sequence_to_routines(
    instructions: tuple[Instruction, ...] | list[Instruction],
    *,
    start_state: Label,
    exit_label: Label,
    names: NameSupply,
    block_label: str | None = None,
    instruction_offset: int = 0,
) -> tuple[Routine, ...]:
    """Lower a straight-line instruction sequence into connected routines.

    Fallthrough routines receive generated continuation labels. Branching and
    halt routines must appear at the end because they do not continue to the
    next instruction.
    """

    routines: list[Routine] = []
    current_state = start_state
    instructions = tuple(instructions)
    for index, instruction in enumerate(instructions):
        cont = exit_label if index + 1 == len(instructions) else names.fresh(f"{start_state}_cont_{index}")
        routine = lower_instruction_to_routine(instruction, state=current_state, cont=cont)
        if not routine.falls_through and index + 1 < len(instructions):
            raise ValueError(f"terminal instruction before end of block: {instruction!r}")
        if block_label is not None:
            routine = _attach_instruction_source(
                routine,
                block_label=block_label,
                instruction_index=instruction_offset + index,
                instruction=instruction,
            )
        routines.append(routine)
        current_state = cont
    return tuple(routines)


def block_to_routines(block: Block, names: NameSupply) -> tuple[Routine, ...]:
    """Lower one labeled Meta-ASM block into routines."""

    routines: list[Routine] = []
    start_state = block.label
    setup = block_entry_setup(block)
    body_start = start_state
    if setup is not None:
        body_start = names.fresh(f"{block.label}_body")
        routines.append(
            _attach_instruction_source(
                lower_instruction_to_routine(setup, state=start_state, cont=body_start),
                block_label=block.label,
                instruction_index=None,
                instruction=setup,
            )
        )
    if block.label != "MATCHED_RULE":
        routines.extend(
            instruction_sequence_to_routines(
                block.instructions,
                start_state=body_start,
                exit_label=names.fresh(f"{block.label}_exit"),
                names=names,
                block_label=block.label,
            )
        )
        return tuple(routines)

    copied_fields = names.fresh("matched_rule_copied_fields")
    resume = names.fresh("matched_rule_resume")
    routines.extend(
        instruction_sequence_to_routines(
            block.instructions[:3],
            start_state=body_start,
            exit_label=copied_fields,
            names=names,
            block_label=block.label,
        )
    )
    routines.append(
        _attach_instruction_source(
            deactivate_active_rule_routine(copied_fields, resume),
            block_label=block.label,
            instruction_index=None,
            instruction=None,
            instruction_text="DEACTIVATE_ACTIVE_RULE cleanup",
        )
    )
    routines.extend(
        instruction_sequence_to_routines(
            block.instructions[3:],
            start_state=resume,
            exit_label=names.fresh("MATCHED_RULE_exit"),
            names=names,
            block_label=block.label,
            instruction_offset=3,
        )
    )
    return tuple(routines)


def program_to_routines(program: Program, names: NameSupply | None = None) -> tuple[Routine, ...]:
    """Lower every block in a Meta-ASM program into Routine IR."""

    names = NameSupply("program") if names is None else names
    routines: list[Routine] = []
    for block in program.blocks:
        routines.extend(block_to_routines(block, names))
    return tuple(routines)


__all__ = ["block_entry_setup", "block_to_routines", "instruction_sequence_to_routines", "program_to_routines"]
