"""Build the future Meta-ASM interpreter rules."""

from __future__ import annotations

from dataclasses import dataclass

from .outer_tape import TMProgram

@dataclass(frozen=True)
class MetaInterpreterRules:
    """Raw TM rules for the interpreter side of the system."""

    tm_program: TMProgram; start_state: str = "U_START"; halt_state: str = "U_HALT"


def build_meta_interpreter_rules(encoding) -> MetaInterpreterRules:
    raise NotImplementedError(f"Next step: generate interpreter rules for {encoding!r}.")
