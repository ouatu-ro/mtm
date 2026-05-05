"""End-to-end lowering from Meta-ASM Program to raw TM program.

This is the only module that knows the whole backend flow:

    Program -> Routine -> RoutineCFG -> validated CFGs -> TMBuilder

Other modules own individual layers. Keeping the orchestration here makes the
serialization/runtime artifact path depend on one clear compiler entry point
instead of scattered helper functions.
"""

from __future__ import annotations

from typing import Iterable

from ..meta_asm import Program
from ..raw_transition_tm import TMBuilder, TMTransitionProgram
from .cfg import RoutineCFG, assemble_cfg, compile_routine, validate_cfg
from .constants import ACTIVE_RULE
from .block_lowering import program_to_routines
from .routines import NameSupply


def program_to_cfgs(program: Program, *, halt_state: str = "U_HALT") -> tuple[RoutineCFG, ...]:
    """Lower a Program into per-routine CFGs without emitting raw transitions."""

    program_names = NameSupply("program")
    cfgs: list[RoutineCFG] = []
    for index, routine in enumerate(program_to_routines(program, program_names)):
        cfgs.append(
            compile_routine(
                routine,
                NameSupply(f"routine_{index}_{routine.name}"),
                halt_state=halt_state,
            )
        )
    return tuple(cfgs)


def validate_program_cfgs(cfgs: tuple[RoutineCFG, ...], alphabet: Iterable[str]) -> None:
    """Validate all CFGs together, including cross-routine transition clashes."""

    alphabet = tuple(alphabet)
    seen: dict[tuple[str, str], int] = {}
    for cfg_index, cfg in enumerate(cfgs):
        validate_cfg(cfg, alphabet)
        for transition in cfg.transitions:
            for read in transition.reads.expand(alphabet):
                key = (transition.source, read)
                if key in seen:
                    raise ValueError(
                        f"duplicate program CFG transition for {key!r} "
                        f"in routine CFG {cfg_index}; first seen in routine CFG {seen[key]}"
                    )
                seen[key] = cfg_index


def assemble_program(builder: TMBuilder, program: Program) -> None:
    """Compile and emit a Program into an existing TMBuilder."""

    cfgs = program_to_cfgs(program, halt_state=builder.halt_state)
    validate_program_cfgs(cfgs, builder.alphabet)
    for cfg in cfgs:
        assemble_cfg(builder, cfg)


def lower_program_to_raw_tm(
    program: Program,
    alphabet: Iterable[str],
    *,
    halt_state: str = "U_HALT",
    blank: str = "_RUNTIME_BLANK",
) -> TMTransitionProgram:
    """Compile a Meta-ASM Program into a raw transition-machine artifact."""

    builder = TMBuilder([*alphabet, ACTIVE_RULE], halt_state=halt_state, blank=blank)
    assemble_program(builder, program)
    return builder.build(program.entry_label)


__all__ = ["assemble_program", "lower_program_to_raw_tm", "program_to_cfgs", "validate_program_cfgs"]
