"""Small Meta-ASM IR for the universal interpreter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .compiled_band import CUR_STATE, CUR_SYMBOL, END_RULES, MOVE, MOVE_DIR, NEXT, NEXT_STATE, READ, STATE, WRITE, WRITE_SYMBOL
from .tape_encoding import Encoding, L, R, encode_direction, encode_state

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

    def lower(
        self,
        alphabet: list[str] | tuple[str, ...],
        *,
        halt_state: str = "U_HALT",
        blank: str = "_OUTER_BLANK",
    ):
        from .lowering import lower_program_to_raw_tm

        return lower_program_to_raw_tm(
            self,
            alphabet,
            halt_state=halt_state,
            blank=blank,
        )

    def to_artifact(
        self,
        alphabet: list[str] | tuple[str, ...],
        *,
        halt_state: str = "U_HALT",
        blank: str = "_OUTER_BLANK",
        target_abi=None,
        minimal_abi=None,
    ):
        return self.lower(alphabet, halt_state=halt_state, blank=blank).to_artifact(
            target_abi=target_abi,
            minimal_abi=minimal_abi,
        )


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
            Block("LOOKUP_RULE", (
                BranchAt(END_RULES, "STUCK", "CHECK_STATE"),
            )),
            Block("CHECK_STATE", (
                CompareGlobalLocal(CUR_STATE, STATE, encoding.state_width),
                BranchCmp("CHECK_READ", "NEXT_RULE"),
            )),
            Block("CHECK_READ", (
                CompareGlobalLocal(CUR_SYMBOL, READ, encoding.symbol_width),
                BranchCmp("MATCHED_RULE", "NEXT_RULE"),
            )),
            Block("NEXT_RULE", (
                FindNextRule(),
                Goto("LOOKUP_RULE"),
            )),
            Block("MATCHED_RULE", (
                CopyLocalGlobal(WRITE, WRITE_SYMBOL, encoding.symbol_width),
                CopyLocalGlobal(NEXT, NEXT_STATE, encoding.state_width),
                CopyLocalGlobal(MOVE, MOVE_DIR, encoding.direction_width),
                FindHeadCell(),
                CopyGlobalToHeadSymbol(WRITE_SYMBOL, encoding.symbol_width),
                CopyGlobalGlobal(NEXT_STATE, CUR_STATE, encoding.state_width),
                CompareGlobalLiteral(CUR_STATE, halt_bits),
                BranchCmp("HALT", "DISPATCH_MOVE"),
            )),
            Block("DISPATCH_MOVE", (
                CompareGlobalLiteral(MOVE_DIR, left_bits),
                BranchCmp("MOVE_LEFT", "CHECK_RIGHT"),
            )),
            Block("CHECK_RIGHT", (
                CompareGlobalLiteral(MOVE_DIR, right_bits),
                BranchCmp("MOVE_RIGHT", "START_STEP"),
            )),
            Block("MOVE_LEFT", (
                FindHeadCell(),
                MoveSimHeadLeft(),
                Goto("START_STEP"),
            )),
            Block("MOVE_RIGHT", (
                FindHeadCell(),
                MoveSimHeadRight(),
                Goto("START_STEP"),
            )),
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
]
