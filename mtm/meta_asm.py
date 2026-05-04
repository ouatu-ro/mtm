"""Small Meta-ASM IR for the universal interpreter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .outer_tape import CUR_STATE, CUR_SYMBOL, Encoding, encode_direction, encode_state, L, R

LabelName: TypeAlias = str
Marker: TypeAlias = str
BitString: TypeAlias = tuple[str, ...]
DirectionName: TypeAlias = str


@dataclass(frozen=True)
class Goto:
    label: LabelName

@dataclass(frozen=True)
class Halt:
    pass

@dataclass(frozen=True)
class Seek:
    marker: Marker; direction: DirectionName

@dataclass(frozen=True)
class SeekOneOf:
    markers: tuple[Marker, ...]; direction: DirectionName

@dataclass(frozen=True)
class FindFirstRule:
    pass

@dataclass(frozen=True)
class FindNextRule:
    pass

@dataclass(frozen=True)
class FindHeadCell:
    pass

@dataclass(frozen=True)
class CompareGlobalLocal:
    global_marker: Marker; local_marker: Marker; width: int

@dataclass(frozen=True)
class CompareGlobalLiteral:
    global_marker: Marker; literal_bits: BitString

@dataclass(frozen=True)
class BranchCmp:
    label_equal: LabelName; label_not_equal: LabelName

@dataclass(frozen=True)
class CopyLocalGlobal:
    local_marker: Marker; global_marker: Marker; width: int

@dataclass(frozen=True)
class CopyGlobalGlobal:
    src_marker: Marker; dst_marker: Marker; width: int

@dataclass(frozen=True)
class CopyHeadSymbolTo:
    global_marker: Marker; width: int

@dataclass(frozen=True)
class CopyGlobalToHeadSymbol:
    global_marker: Marker; width: int

@dataclass(frozen=True)
class WriteGlobal:
    global_marker: Marker; literal_bits: BitString

@dataclass(frozen=True)
class MoveSimHeadLeft:
    pass

@dataclass(frozen=True)
class MoveSimHeadRight:
    pass

@dataclass(frozen=True)
class BranchAt:
    marker: Marker; label_true: LabelName; label_false: LabelName


@dataclass(frozen=True)
class Unimplemented:
    note: str


Instruction: TypeAlias = (
    Goto
    | Halt
    | Seek | SeekOneOf
    | FindFirstRule | FindNextRule | FindHeadCell
    | CompareGlobalLocal | CompareGlobalLiteral
    | BranchCmp
    | CopyLocalGlobal | CopyGlobalGlobal | CopyHeadSymbolTo | CopyGlobalToHeadSymbol
    | WriteGlobal
    | MoveSimHeadLeft | MoveSimHeadRight
    | BranchAt
    | Unimplemented
)


@dataclass(frozen=True)
class Block:
    label: LabelName
    instructions: tuple[Instruction, ...]


@dataclass(frozen=True)
class Program:
    blocks: tuple[Block, ...]
    entry_label: LabelName


def bits(value: str) -> BitString: return tuple(value)


def format_instruction(instruction: Instruction) -> str:
    match instruction:
        case Goto(label):
            return f"GOTO {label}"
        case Halt():
            return "HALT"
        case Seek(marker, direction):
            return f"SEEK {marker} {direction}"
        case SeekOneOf(markers, direction):
            return f"SEEK_ONE_OF [{', '.join(markers)}] {direction}"
        case FindFirstRule():
            return "FIND_FIRST_RULE"
        case FindNextRule():
            return "FIND_NEXT_RULE"
        case FindHeadCell():
            return "FIND_HEAD_CELL"
        case CompareGlobalLocal(global_marker, local_marker, width):
            return f"COMPARE_GLOBAL_LOCAL {global_marker} {local_marker} {width}"
        case CompareGlobalLiteral(global_marker, literal_bits):
            return f"COMPARE_GLOBAL_LITERAL {global_marker} {''.join(literal_bits)}"
        case BranchCmp(label_equal, label_not_equal):
            return f"BRANCH_CMP {label_equal} {label_not_equal}"
        case CopyLocalGlobal(local_marker, global_marker, width):
            return f"COPY_LOCAL_GLOBAL {local_marker} {global_marker} {width}"
        case CopyGlobalGlobal(src_marker, dst_marker, width):
            return f"COPY_GLOBAL_GLOBAL {src_marker} {dst_marker} {width}"
        case CopyHeadSymbolTo(global_marker, width):
            return f"COPY_HEAD_SYMBOL_TO {global_marker} {width}"
        case CopyGlobalToHeadSymbol(global_marker, width):
            return f"COPY_GLOBAL_TO_HEAD_SYMBOL {global_marker} {width}"
        case WriteGlobal(global_marker, literal_bits):
            return f"WRITE_GLOBAL {global_marker} {''.join(literal_bits)}"
        case MoveSimHeadLeft():
            return "MOVE_SIM_HEAD_LEFT"
        case MoveSimHeadRight():
            return "MOVE_SIM_HEAD_RIGHT"
        case BranchAt(marker, label_true, label_false):
            return f"BRANCH_AT {marker} {label_true} {label_false}"
        case Unimplemented(note):
            return f"UNIMPLEMENTED {note}"


def format_program(program: Program) -> str:
    parts = []
    for block in program.blocks:
        body = "\n".join(f"  {format_instruction(instruction)}" for instruction in block.instructions)
        parts.append(f"LABEL {block.label}\n{body}")
    return "\n\n".join(parts)


def stub_block(label: LabelName, note: str) -> Block:
    return Block(label, (Unimplemented(note),))


def build_universal_meta_asm(encoding: Encoding) -> Program:
    halt_bits = encode_state(encoding, encoding.halt_state)
    left_bits, right_bits = encode_direction(encoding, L), encode_direction(encoding, R)
    return Program(
        entry_label="START_STEP",
        blocks=(
            Block("START_STEP", (
                CompareGlobalLiteral(CUR_STATE, halt_bits),
                BranchCmp("HALT", "FIND_HEAD"),
            )),
            Block("FIND_HEAD", (
                FindHeadCell(),
                CopyHeadSymbolTo(CUR_SYMBOL, encoding.symbol_width),
                FindFirstRule(),
                Goto("LOOKUP_RULE"),
            )),
            stub_block("LOOKUP_RULE", "branch on #END_RULES, then inspect the current rule"),
            stub_block("CHECK_STATE", "compare #CUR_STATE with the rule's #STATE field"),
            stub_block("CHECK_READ", "compare #CUR_SYMBOL with the rule's #READ field"),
            stub_block("NEXT_RULE", "advance to the next rule and continue lookup"),
            stub_block("MATCHED_RULE", "copy WRITE/NEXT/MOVE out of the matched rule and apply them"),
            stub_block("DISPATCH_MOVE", f"branch on #MOVE_DIR using L={''.join(left_bits)} and R={''.join(right_bits)}"),
            stub_block("CHECK_RIGHT", f"fallthrough branch for right-move bits {''.join(right_bits)}"),
            stub_block("MOVE_LEFT", "move the simulated head left, then restart the interpreter cycle"),
            stub_block("MOVE_RIGHT", "move the simulated head right, then restart the interpreter cycle"),
            Block("HALT", (Halt(),)),
            Block("STUCK", (Halt(),)),
        ),
    )


__all__ = [
    "BitString",
    "Block",
    "BranchAt",
    "BranchCmp",
    "CompareGlobalLiteral",
    "CompareGlobalLocal",
    "CopyGlobalGlobal",
    "CopyGlobalToHeadSymbol",
    "CopyHeadSymbolTo",
    "CopyLocalGlobal",
    "DirectionName",
    "FindFirstRule",
    "FindHeadCell",
    "FindNextRule",
    "Goto",
    "Halt",
    "Instruction",
    "LabelName",
    "Marker",
    "MoveSimHeadLeft",
    "MoveSimHeadRight",
    "Program",
    "Seek",
    "SeekOneOf",
    "Unimplemented",
    "WriteGlobal",
    "bits",
    "build_universal_meta_asm",
    "format_instruction",
    "format_program",
    "stub_block",
]
