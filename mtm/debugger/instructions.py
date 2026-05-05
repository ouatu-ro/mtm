"""Debugger-facing descriptions of Meta-ASM instructions.

The debugger does not show raw instruction objects directly. It translates
them into short teaching sentences so a trace can explain what each Meta-ASM
step is trying to do.
"""

from __future__ import annotations

from ..meta_asm import BranchAt, BranchCmp, CompareGlobalLiteral, CompareGlobalLocal, CopyGlobalGlobal, CopyGlobalToHeadSymbol, CopyHeadSymbolTo, CopyLocalGlobal, FindFirstRule, FindHeadCell, FindNextRule, Goto, Halt, MoveSimHeadLeft, MoveSimHeadRight, Seek, SeekOneOf, Unimplemented, WriteGlobal


def explain_meta_instruction(instruction) -> str | None:
    """Translate one Meta-ASM instruction into a short teaching sentence."""

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


__all__ = ["explain_meta_instruction"]
