"""Source metadata for lowered routines, CFGs, and raw transition rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..meta_asm import Instruction
from ..raw_transition_tm import TransitionKey, TMTransitionProgram

if TYPE_CHECKING:
    from .cfg import RoutineCFG
    from .ops import Op


@dataclass(frozen=True)
class RoutineSource:
    """Source metadata for one lowered Routine."""

    block_label: str
    routine_name: str
    routine_index: int | None
    instruction_index: int | None
    instruction: Instruction | None
    instruction_text: str | None


@dataclass(frozen=True)
class OpSource:
    """Source metadata for one Routine op."""

    routine_name: str
    routine_index: int | None
    block_label: str
    instruction_index: int | None
    instruction: Instruction | None
    instruction_text: str | None
    op_index: int
    op: Op


@dataclass(frozen=True)
class CFGTransitionSource:
    """Source metadata for one structured CFG transition."""

    routine_name: str
    routine_index: int | None
    block_label: str
    instruction_index: int | None
    instruction: Instruction | None
    instruction_text: str | None
    op_index: int
    op: Op


@dataclass(frozen=True)
class RawTransitionSource:
    """Source metadata for one raw transition row."""

    state: str
    read_symbol: str
    routine_name: str
    routine_index: int | None
    block_label: str
    instruction_index: int | None
    instruction: Instruction | None
    instruction_text: str | None
    op_index: int
    op: Op


@dataclass(frozen=True)
class TransitionSourceMap:
    """Query raw transition metadata by concrete ``(state, read_symbol)`` key."""

    entries: dict[TransitionKey, RawTransitionSource]

    def lookup(self, state: str, read_symbol: str) -> RawTransitionSource | None:
        """Return source metadata for one raw transition row if present."""

        return self.entries.get((state, read_symbol))


@dataclass(frozen=True)
class LoweredProgramWithSourceMap:
    """Raw TM plus source metadata captured during lowering."""

    raw_program: TMTransitionProgram
    cfgs: tuple["RoutineCFG", ...]
    source_map: TransitionSourceMap


def bind_routine_index(source: RoutineSource | OpSource | None, *, routine_name: str, routine_index: int):
    """Return ``source`` with the concrete routine identity filled in."""

    if source is None:
        return None
    match source:
        case RoutineSource():
            return RoutineSource(
                block_label=source.block_label,
                routine_name=routine_name,
                routine_index=routine_index,
                instruction_index=source.instruction_index,
                instruction=source.instruction,
                instruction_text=source.instruction_text,
            )
        case OpSource():
            return OpSource(
                routine_name=routine_name,
                routine_index=routine_index,
                block_label=source.block_label,
                instruction_index=source.instruction_index,
                instruction=source.instruction,
                instruction_text=source.instruction_text,
                op_index=source.op_index,
                op=source.op,
            )
        case _:
            raise TypeError(f"unsupported routine source: {source!r}")


def transition_source_from_op(source: OpSource | None) -> CFGTransitionSource | None:
    """Project per-op source metadata onto one CFG transition."""

    if source is None:
        return None
    return CFGTransitionSource(
        routine_name=source.routine_name,
        routine_index=source.routine_index,
        block_label=source.block_label,
        instruction_index=source.instruction_index,
        instruction=source.instruction,
        instruction_text=source.instruction_text,
        op_index=source.op_index,
        op=source.op,
    )


def raw_transition_source(
    state: str,
    read_symbol: str,
    source: CFGTransitionSource | None,
) -> RawTransitionSource | None:
    """Attach concrete row coordinates to one transition source."""

    if source is None:
        return None
    return RawTransitionSource(
        state=state,
        read_symbol=read_symbol,
        routine_name=source.routine_name,
        routine_index=source.routine_index,
        block_label=source.block_label,
        instruction_index=source.instruction_index,
        instruction=source.instruction,
        instruction_text=source.instruction_text,
        op_index=source.op_index,
        op=source.op,
    )


__all__ = [
    "CFGTransitionSource",
    "LoweredProgramWithSourceMap",
    "OpSource",
    "RawTransitionSource",
    "RoutineSource",
    "TransitionSourceMap",
    "bind_routine_index",
    "raw_transition_source",
    "transition_source_from_op",
]
