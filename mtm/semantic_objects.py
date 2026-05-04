"""Semantic object model for source TMs, UTM encodings, and runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from .compiled_band import EncodedBand
from .pretty import parse_registers, parse_rules, parse_tape
from .raw_tm import RawTM
from .tape_encoding import Encoding, TMProgram


@dataclass(frozen=True)
class TMBand:
    """Source-level tape/configuration."""

    cells: tuple[str, ...]
    head: int
    blank: str


@dataclass(frozen=True)
class TMInstance:
    """Source-level program plus source-level band."""

    program: TMProgram
    band: TMBand


@dataclass(frozen=True)
class TMAbi:
    """Target encoding family / machine family."""

    state_width: int
    symbol_width: int
    dir_width: int
    grammar_version: str = "mtm-v1"
    family_label: str = ""


AbiRequirement = TMAbi


@dataclass(frozen=True)
class UTMRegisters:
    """Semantic register block used by the universal interpreter."""

    cur_state: str
    cur_symbol: str
    write_symbol: str
    next_state: str
    move_dir: int
    cmp_flag: str
    tmp_bits: tuple[str, ...]


@dataclass(frozen=True)
class UTMEncodedRule:
    """One semantic encoded object-program rule."""

    state: str
    read_symbol: str
    next_state: str
    write_symbol: str
    move_dir: int


@dataclass(frozen=True)
class UTMSimulatedTape:
    """Semantic view of the encoded object tape."""

    cells: tuple[str, ...]
    head: int
    blank: str


@dataclass(frozen=True)
class UTMEncoded:
    """Semantic compiled object for the universal machine."""

    encoding: Encoding
    registers: UTMRegisters
    rules: tuple[UTMEncodedRule, ...]
    simulated_tape: UTMSimulatedTape
    minimal_abi: TMAbi
    target_abi: TMAbi

    @property
    def simulated_head(self) -> int: return self.simulated_tape.head

    @property
    def current_state(self) -> str: return self.registers.cur_state


@dataclass(frozen=True)
class UTMEncodingArtifact:
    """Serialized artifact form of a semantic UTM-encoded object."""

    encoding: Encoding
    left_band: tuple[str, ...]
    right_band: tuple[str, ...]
    start_head: int
    target_abi: TMAbi
    minimal_abi: TMAbi

    def to_encoded_band(self) -> EncodedBand:
        return encoded_band_from_utm_artifact(self)


@dataclass(frozen=True)
class RawTMConfig:
    """Runner-facing raw TM execution state."""

    program: RawTM
    tape: dict[int, str]
    head: int
    state: str


@dataclass(frozen=True)
class DecodedBandView:
    """Decoded semantic view recovered from a compiled UTM artifact or runtime state."""

    registers: UTMRegisters
    rules: tuple[UTMEncodedRule, ...]
    simulated_tape: UTMSimulatedTape
    encoding: Encoding

    @property
    def simulated_head(self) -> int: return self.simulated_tape.head

    @property
    def current_state(self) -> str: return self.registers.cur_state


def abi_from_encoding(encoding: Encoding) -> TMAbi:
    return TMAbi(
        state_width=encoding.state_width,
        symbol_width=encoding.symbol_width,
        dir_width=encoding.direction_width,
        family_label=f"U[Wq={encoding.state_width},Ws={encoding.symbol_width},Wd={encoding.direction_width}]",
    )


def source_band_from_simulated_tape(cells: tuple[str, ...], head: int, *, blank: str) -> TMBand:
    return TMBand(cells=cells, head=head, blank=blank)


def start_head_from_encoded_band(band: EncodedBand) -> int:
    left_addresses = list(range(-len(band.left_band), 0))
    return left_addresses[band.left_band.index("#CUR_STATE")]


def decoded_view_from_encoded_band(band: EncodedBand) -> DecodedBandView:
    registers, rule_start = parse_registers(band.encoding, band.left_band)
    rules = tuple(UTMEncodedRule(*rule) for rule in parse_rules(band.encoding, band.left_band, rule_start))
    cells, head = parse_tape(band.encoding, band.right_band)
    return DecodedBandView(
        registers=UTMRegisters(
            cur_state=registers["CUR_STATE"],
            cur_symbol=registers["CUR_SYMBOL"],
            write_symbol=registers["WRITE_SYMBOL"],
            next_state=registers["NEXT_STATE"],
            move_dir=registers["MOVE_DIR"],
            cmp_flag=registers["CMP_FLAG"],
            tmp_bits=tuple(registers["TMP"]),
        ),
        rules=rules,
        simulated_tape=UTMSimulatedTape(cells=tuple(cells), head=head, blank=band.encoding.blank),
        encoding=band.encoding,
    )


def utm_encoded_from_band(band: EncodedBand, *, minimal_abi: TMAbi | None = None) -> UTMEncoded:
    view = decoded_view_from_encoded_band(band)
    target_abi = abi_from_encoding(band.encoding)
    return UTMEncoded(
        encoding=band.encoding,
        registers=view.registers,
        rules=view.rules,
        simulated_tape=view.simulated_tape,
        minimal_abi=target_abi if minimal_abi is None else minimal_abi,
        target_abi=target_abi,
    )


def utm_artifact_from_band(band: EncodedBand, *, minimal_abi: TMAbi | None = None) -> UTMEncodingArtifact:
    target_abi = abi_from_encoding(band.encoding)
    return UTMEncodingArtifact(
        encoding=band.encoding,
        left_band=tuple(band.left_band),
        right_band=tuple(band.right_band),
        start_head=start_head_from_encoded_band(band),
        target_abi=target_abi,
        minimal_abi=target_abi if minimal_abi is None else minimal_abi,
    )


def encoded_band_from_utm_artifact(artifact: UTMEncodingArtifact) -> EncodedBand:
    return EncodedBand(artifact.encoding, list(artifact.left_band), list(artifact.right_band))


__all__ = [
    "AbiRequirement",
    "DecodedBandView",
    "RawTMConfig",
    "TMBand",
    "TMAbi",
    "TMInstance",
    "UTMEncoded",
    "UTMEncodedRule",
    "UTMEncodingArtifact",
    "UTMRegisters",
    "UTMSimulatedTape",
    "abi_from_encoding",
    "decoded_view_from_encoded_band",
    "encoded_band_from_utm_artifact",
    "source_band_from_simulated_tape",
    "start_head_from_encoded_band",
    "utm_artifact_from_band",
    "utm_encoded_from_band",
]
