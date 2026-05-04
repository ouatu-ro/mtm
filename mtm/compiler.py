"""Compiler object for source TM instances."""

from __future__ import annotations

from dataclasses import dataclass

from .compiled_band import compile_tm_to_universal_tape
from .semantic_objects import TMAbi, TMInstance, UTMEncoded, infer_minimal_abi, utm_encoded_from_band


@dataclass(frozen=True)
class Compiler:
    target_abi: TMAbi | None = None
    initial_state: str | None = None
    halt_state: str | None = None

    def infer_abi(self, instance: TMInstance) -> TMAbi:
        initial_state, halt_state = self._resolve_states(instance)
        return infer_minimal_abi(
            instance.program,
            instance.band,
            initial_state=initial_state,
            halt_state=halt_state,
        )

    def compile(self, instance: TMInstance) -> UTMEncoded:
        initial_state, halt_state = self._resolve_states(instance)
        band = compile_tm_to_universal_tape(
            instance.program,
            instance.band,
            initial_state=initial_state,
            halt_state=halt_state,
            blank=instance.band.blank,
            abi=self.target_abi,
        )
        return utm_encoded_from_band(band)

    def _resolve_states(self, instance: TMInstance) -> tuple[str, str]:
        initial_state = instance.initial_state or self.initial_state
        halt_state = instance.halt_state or self.halt_state
        if initial_state is None or halt_state is None:
            raise ValueError("Compiler requires initial_state and halt_state on the TMInstance or Compiler")
        return initial_state, halt_state


__all__ = ["Compiler"]
