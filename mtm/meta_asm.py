"""Small Meta-ASM IR for the universal interpreter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, TypeAlias

from .utm_band_layout import CUR_STATE, CUR_SYMBOL, END_RULES, MOVE, MOVE_DIR, NEXT, NEXT_STATE, READ, STATE, WRITE, WRITE_SYMBOL
from .source_encoding import Encoding, L, R, encode_direction, encode_state

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
        alphabet: Iterable[str],
        *,
        halt_state: str = "U_HALT",
        blank: str = "_RUNTIME_BLANK",
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
        alphabet: Iterable[str],
        *,
        halt_state: str = "U_HALT",
        blank: str = "_RUNTIME_BLANK",
        target_abi=None,
        minimal_abi=None,
    ):
        return self.lower(alphabet, halt_state=halt_state, blank=blank).to_artifact(
            target_abi=target_abi,
            minimal_abi=minimal_abi,
        )


MetaASMProgram = Program


def bits(value: str) -> BitString: return tuple(value)


@dataclass(frozen=True)
class InstructionFormatSpec:
    opcode: str
    format_operands: Callable[[Instruction], str] = lambda _instruction: ""


def _join_bits(bit_string: BitString) -> str:
    return "".join(bit_string)


def _format_seek_one_of(instruction: Instruction) -> str:
    assert isinstance(instruction, SeekOneOf)
    return f"[{', '.join(instruction.markers)}] {instruction.direction}"


def _format_compare_global_local(instruction: Instruction) -> str:
    assert isinstance(instruction, CompareGlobalLocal)
    return f"{instruction.global_marker} {instruction.local_marker} {instruction.width}"


def _format_compare_global_literal(instruction: Instruction) -> str:
    assert isinstance(instruction, CompareGlobalLiteral)
    return f"{instruction.global_marker} {_join_bits(instruction.literal_bits)}"


def _format_branch_cmp(instruction: Instruction) -> str:
    assert isinstance(instruction, BranchCmp)
    return f"{instruction.label_equal} {instruction.label_not_equal}"


def _format_copy_local_global(instruction: Instruction) -> str:
    assert isinstance(instruction, CopyLocalGlobal)
    return f"{instruction.local_marker} {instruction.global_marker} {instruction.width}"


def _format_copy_global_global(instruction: Instruction) -> str:
    assert isinstance(instruction, CopyGlobalGlobal)
    return f"{instruction.src_marker} {instruction.dst_marker} {instruction.width}"


def _format_copy_head_symbol_to(instruction: Instruction) -> str:
    assert isinstance(instruction, CopyHeadSymbolTo)
    return f"{instruction.global_marker} {instruction.width}"


def _format_copy_global_to_head_symbol(instruction: Instruction) -> str:
    assert isinstance(instruction, CopyGlobalToHeadSymbol)
    return f"{instruction.global_marker} {instruction.width}"


def _format_write_global(instruction: Instruction) -> str:
    assert isinstance(instruction, WriteGlobal)
    return f"{instruction.global_marker} {_join_bits(instruction.literal_bits)}"


def _format_branch_at(instruction: Instruction) -> str:
    assert isinstance(instruction, BranchAt)
    return f"{instruction.marker} {instruction.label_true} {instruction.label_false}"


INSTRUCTION_FORMATS: dict[type[Instruction], InstructionFormatSpec] = {
    Goto: InstructionFormatSpec("GOTO", lambda instruction: instruction.label),
    Halt: InstructionFormatSpec("HALT"),
    Seek: InstructionFormatSpec("SEEK", lambda instruction: f"{instruction.marker} {instruction.direction}"),
    SeekOneOf: InstructionFormatSpec("SEEK_ONE_OF", _format_seek_one_of),
    FindFirstRule: InstructionFormatSpec("FIND_FIRST_RULE"),
    FindNextRule: InstructionFormatSpec("FIND_NEXT_RULE"),
    FindHeadCell: InstructionFormatSpec("FIND_HEAD_CELL"),
    CompareGlobalLocal: InstructionFormatSpec("COMPARE_GLOBAL_LOCAL", _format_compare_global_local),
    CompareGlobalLiteral: InstructionFormatSpec("COMPARE_GLOBAL_LITERAL", _format_compare_global_literal),
    BranchCmp: InstructionFormatSpec("BRANCH_CMP", _format_branch_cmp),
    CopyLocalGlobal: InstructionFormatSpec("COPY_LOCAL_GLOBAL", _format_copy_local_global),
    CopyGlobalGlobal: InstructionFormatSpec("COPY_GLOBAL_GLOBAL", _format_copy_global_global),
    CopyHeadSymbolTo: InstructionFormatSpec("COPY_HEAD_SYMBOL_TO", _format_copy_head_symbol_to),
    CopyGlobalToHeadSymbol: InstructionFormatSpec("COPY_GLOBAL_TO_HEAD_SYMBOL", _format_copy_global_to_head_symbol),
    WriteGlobal: InstructionFormatSpec("WRITE_GLOBAL", _format_write_global),
    MoveSimHeadLeft: InstructionFormatSpec("MOVE_SIM_HEAD_LEFT"),
    MoveSimHeadRight: InstructionFormatSpec("MOVE_SIM_HEAD_RIGHT"),
    BranchAt: InstructionFormatSpec("BRANCH_AT", _format_branch_at),
    Unimplemented: InstructionFormatSpec("UNIMPLEMENTED", lambda instruction: instruction.note),
}


def format_instruction(instruction: Instruction) -> str:
    spec = INSTRUCTION_FORMATS.get(type(instruction))
    if spec is None:
        raise TypeError(f"unsupported Meta-ASM instruction: {instruction!r}")
    operands = spec.format_operands(instruction)
    return spec.opcode if not operands else f"{spec.opcode} {operands}"


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


__all__ = ["BitString", "Block", "BranchAt", "BranchCmp", "CompareGlobalLiteral", "CompareGlobalLocal",
           "CopyGlobalGlobal", "CopyGlobalToHeadSymbol", "CopyHeadSymbolTo", "CopyLocalGlobal", "DirectionName",
           "FindFirstRule", "FindHeadCell", "FindNextRule", "Goto", "Halt", "Instruction", "LabelName", "Marker",
           "MetaASMProgram", "MoveSimHeadLeft", "MoveSimHeadRight", "Program", "Seek", "SeekOneOf", "Unimplemented",
           "WriteGlobal", "bits", "build_universal_meta_asm", "format_instruction", "format_program"]
