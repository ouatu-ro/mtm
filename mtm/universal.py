"""Universal interpreter facade.

This object ties together the semantic UTM input, the Meta-ASM universal
program, lowering to a raw transition table, and optional execution. It is the
high-level object to use when you want "the universal machine for this
encoding" rather than the individual compiler stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .lowering import ACTIVE_RULE
from .meta_asm import Program, build_universal_meta_asm
from .semantic_objects import UTMEncoded, UTMBandArtifact, UTMProgramArtifact
from .source_encoding import Encoding
from .utm_band_layout import UTM_STRUCTURAL_ALPHABET


@dataclass(frozen=True)
class UniversalInterpreter:
    """Universal machine specialized to one source-machine encoding."""

    encoding: Encoding

    @classmethod
    def for_encoding(cls, encoding: Encoding) -> "UniversalInterpreter":
        """Construct an interpreter for an existing Encoding."""

        return cls(encoding=encoding)

    @classmethod
    def for_encoded(cls, encoded: UTMEncoded | UTMBandArtifact) -> "UniversalInterpreter":
        """Construct an interpreter matching an encoded UTM input object."""

        return cls.for_encoding(encoded.encoding)

    def to_meta_asm(self) -> Program:
        """Return the Meta-ASM program for this universal interpreter."""

        return build_universal_meta_asm(self.encoding)

    def alphabet_for_band(self, band_artifact: UTMBandArtifact) -> tuple[str, ...]:
        """Compute the raw TM alphabet needed to run one band artifact."""

        return tuple(sorted(set(band_artifact.to_encoded_tape().linear()) | set(UTM_STRUCTURAL_ALPHABET) | {ACTIVE_RULE}))

    def lower(
        self,
        alphabet: Iterable[str],
        *,
        target_abi=None,
        minimal_abi=None,
        halt_state: str = "U_HALT",
        blank: str = "_RUNTIME_BLANK",
    ) -> UTMProgramArtifact:
        """Lower the universal interpreter to a raw transition program."""

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
        blank: str = "_RUNTIME_BLANK",
    ) -> UTMProgramArtifact:
        """Lower the interpreter with the alphabet and ABI from one input band."""

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
        blank: str = "_RUNTIME_BLANK",
    ) -> dict[str, object]:
        """Lower and run this interpreter on one band artifact."""

        return self.lower_for_band(
            band_artifact,
            halt_state=halt_state,
            blank=blank,
        ).run(band_artifact, fuel=fuel)


__all__ = ["UniversalInterpreter"]
