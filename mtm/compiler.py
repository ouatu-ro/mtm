"""Compiler facade for source TM instances.

The Compiler is the teaching-facing entry point for turning a source
``TMInstance`` into a semantic ``UTMEncoded`` object. Lower-level band layout
and ABI inference helpers stay behind this facade.
"""

from __future__ import annotations

from dataclasses import dataclass

from .utm_band_layout import compile_tm_to_universal_tape
from .semantic_objects import TMAbi, TMInstance, UTMEncoded, infer_minimal_abi, utm_encoded_from_tape


@dataclass(frozen=True)
class Compiler:
    """Compile source TM instances into semantic UTM-encoded objects."""

    target_abi: TMAbi | None = None
    initial_state: str | None = None
    halt_state: str | None = None

    def infer_abi(self, instance: TMInstance) -> TMAbi:
        """Infer the minimal ABI needed by a source machine instance."""

        self._validate_instance(instance)
        initial_state, halt_state = self._resolve_states(instance)
        return infer_minimal_abi(
            instance.program,
            instance.tape,
            initial_state=initial_state,
            halt_state=halt_state,
        )

    def compile(self, instance: TMInstance) -> UTMEncoded:
        """Compile a source machine instance into semantic UTM input."""

        self._validate_instance(instance)
        initial_state, halt_state = self._resolve_states(instance)
        tape = compile_tm_to_universal_tape(
            instance.program,
            instance.tape,
            initial_state=initial_state,
            halt_state=halt_state,
            abi=self.target_abi,
        )
        return utm_encoded_from_tape(tape)

    def _resolve_states(self, instance: TMInstance) -> tuple[str, str]:
        """Resolve initial/halt states from the instance or compiler defaults."""

        initial_state = instance.initial_state or instance.program.initial_state or self.initial_state
        halt_state = instance.halt_state or instance.program.halt_state or self.halt_state
        if initial_state is None or halt_state is None:
            raise ValueError("Compiler requires initial_state and halt_state on the TMInstance, TMProgram, or Compiler")
        return initial_state, halt_state

    def _validate_instance(self, instance: TMInstance) -> None:
        """Reject source instances whose program and band contracts disagree."""

        if instance.program.blank != instance.tape.blank:
            raise ValueError(
                f"source blank mismatch: TMProgram.blank={instance.program.blank!r} "
                f"!= SourceTape.blank={instance.tape.blank!r}"
            )


__all__ = ["Compiler"]
