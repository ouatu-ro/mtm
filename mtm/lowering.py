"""First raw-TM lowerings for small Meta-ASM instructions."""

from __future__ import annotations

from .meta_asm import BranchCmp, Goto, Halt, Instruction, WriteGlobal
from .outer_tape import CMP_FLAG
from .raw_tm import R, S, TMBuilder


def lower_instruction(builder: TMBuilder, instruction: Instruction, *, state: str, continuation_label: str) -> None:
    """Lower one small Meta-ASM instruction into raw TM transitions.

    Current fragment contracts:
    - `HALT`: no precondition on head position.
    - `GOTO`: no precondition on head position.
    - `BRANCH_CMP`: head is on the `#CMP_FLAG` marker.
    - `WRITE_GLOBAL`: head is on the target global marker.
    """

    match instruction:
        case Halt():
            builder.emit_all(state, builder.halt_state, move=S)
        case Goto(label):
            builder.emit_all(state, builder.label_state(label), move=S)
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
