"""Object wrapper for the universal interpreter build/lower/run flow."""

from __future__ import annotations

from dataclasses import dataclass

from .lowering import ACTIVE_RULE
from .meta_asm import Program, build_universal_meta_asm
from .semantic_objects import UTMEncoded, UTMBandArtifact, UTMProgramArtifact
from .tape_encoding import Encoding


@dataclass(frozen=True)
class UniversalInterpreter:
    encoding: Encoding

    @classmethod
    def for_encoding(cls, encoding: Encoding) -> "UniversalInterpreter":
        return cls(encoding=encoding)

    @classmethod
    def for_encoded(cls, encoded: UTMEncoded | UTMBandArtifact) -> "UniversalInterpreter":
        return cls.for_encoding(encoded.encoding)

    def to_meta_asm(self) -> Program:
        return build_universal_meta_asm(self.encoding)

    def alphabet_for_band(self, band_artifact: UTMBandArtifact) -> tuple[str, ...]:
        return tuple(sorted(set(band_artifact.to_encoded_band().linear()) | {"0", "1", ACTIVE_RULE}))

    def lower(
        self,
        alphabet: list[str] | tuple[str, ...],
        *,
        target_abi=None,
        minimal_abi=None,
        halt_state: str = "U_HALT",
        blank: str = "_OUTER_BLANK",
    ) -> UTMProgramArtifact:
        return self.to_meta_asm().to_artifact(
            alphabet,
            halt_state=halt_state,
            blank=blank,
            target_abi=target_abi,
            minimal_abi=minimal_abi,
        )

    def lower_for_band(
        self,
        band_artifact: UTMBandArtifact,
        *,
        halt_state: str = "U_HALT",
        blank: str = "_OUTER_BLANK",
    ) -> UTMProgramArtifact:
        return self.lower(
            self.alphabet_for_band(band_artifact),
            target_abi=band_artifact.target_abi,
            minimal_abi=band_artifact.minimal_abi,
            halt_state=halt_state,
            blank=blank,
        )

    def run(
        self,
        band_artifact: UTMBandArtifact,
        *,
        fuel: int = 100,
        halt_state: str = "U_HALT",
        blank: str = "_OUTER_BLANK",
    ) -> dict[str, object]:
        return self.lower_for_band(
            band_artifact,
            halt_state=halt_state,
            blank=blank,
        ).run(band_artifact, fuel=fuel)


__all__ = ["UniversalInterpreter"]
