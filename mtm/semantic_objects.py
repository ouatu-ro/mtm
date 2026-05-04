"""Semantic object model for source TMs, UTM encodings, and runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from .compiled_band import (
    CELL,
    CMP_FLAG,
    CUR_STATE,
    CUR_SYMBOL,
    END_CELL,
    END_REGS,
    END_RULE,
    END_RULES,
    HEAD,
    MOVE,
    MOVE_DIR,
    NEXT,
    NEXT_STATE,
    NO_HEAD,
    READ,
    REGS,
    RULE,
    RULES,
    STATE,
    TAPE,
    TMP,
    WRITE,
    WRITE_SYMBOL,
    END_TAPE,
    EncodedBand,
    wrap_field,
)
from .pretty import parse_registers, parse_rules, parse_tape
from .raw_tm import TMTransitionProgram
from .tape_encoding import (
    AbiRequirement,
    Encoding,
    TMAbi,
    TMProgram,
    encode_direction,
    encode_state,
    encode_symbol,
    infer_minimal_abi as infer_minimal_encoding_abi,
)


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
    initial_state: str | None = None
    halt_state: str | None = None


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

    def to_encoded_band(self) -> EncodedBand:
        left_band = _register_band_from_semantics(self.encoding, self.registers)
        left_band += _rule_band_from_semantics(self.encoding, self.rules)
        right_band = _tape_band_from_semantics(self.encoding, self.simulated_tape)
        return EncodedBand(
            self.encoding,
            left_band,
            right_band,
            minimal_abi=self.minimal_abi,
            target_abi=self.target_abi,
        )

    def to_band_artifact(self) -> "UTMBandArtifact":
        return utm_artifact_from_band(self.to_encoded_band(), minimal_abi=self.minimal_abi)

    def decoded_view(self) -> "DecodedBandView":
        return DecodedBandView(
            registers=self.registers,
            rules=self.rules,
            simulated_tape=self.simulated_tape,
            encoding=self.encoding,
        )


@dataclass(frozen=True)
class UTMBandArtifact:
    """Serialized artifact form of a semantic UTM-encoded object."""

    encoding: Encoding
    left_band: tuple[str, ...]
    right_band: tuple[str, ...]
    start_head: int
    target_abi: TMAbi
    minimal_abi: TMAbi

    def to_encoded_band(self) -> EncodedBand:
        return encoded_band_from_utm_artifact(self)

    def to_runtime_tape(self) -> dict[int, str]:
        return self.to_encoded_band().to_runtime_tape()

    def write(self, path: str | "Path") -> None:
        from .artifacts import write_utm_artifact

        write_utm_artifact(path, self)

    @classmethod
    def read(cls, path: str | "Path") -> "UTMBandArtifact":
        from .artifacts import read_utm_artifact

        return read_utm_artifact(path)


UTMEncodingArtifact = UTMBandArtifact


@dataclass(frozen=True)
class TMRunConfig:
    """Runner-facing raw TM execution state."""

    program: TMTransitionProgram
    tape: dict[int, str]
    head: int
    state: str


RawTMConfig = TMRunConfig


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


def _register_band_from_semantics(encoding: Encoding, registers: UTMRegisters) -> list[str]:
    return [
        REGS,
        *wrap_field(CUR_STATE, encode_state(encoding, registers.cur_state)),
        *wrap_field(CUR_SYMBOL, encode_symbol(encoding, registers.cur_symbol)),
        *wrap_field(WRITE_SYMBOL, encode_symbol(encoding, registers.write_symbol)),
        *wrap_field(NEXT_STATE, encode_state(encoding, registers.next_state)),
        *wrap_field(MOVE_DIR, encode_direction(encoding, registers.move_dir)),
        *wrap_field(CMP_FLAG, (registers.cmp_flag,)),
        *wrap_field(TMP, registers.tmp_bits),
        END_REGS,
    ]


def _rule_band_from_semantics(encoding: Encoding, rules: tuple[UTMEncodedRule, ...]) -> list[str]:
    band = [RULES]
    for rule in rules:
        band.extend([
            RULE,
            *wrap_field(STATE, encode_state(encoding, rule.state)),
            *wrap_field(READ, encode_symbol(encoding, rule.read_symbol)),
            *wrap_field(WRITE, encode_symbol(encoding, rule.write_symbol)),
            *wrap_field(NEXT, encode_state(encoding, rule.next_state)),
            *wrap_field(MOVE, encode_direction(encoding, rule.move_dir)),
            END_RULE,
        ])
    return band + [END_RULES]


def _tape_band_from_semantics(encoding: Encoding, tape: UTMSimulatedTape) -> list[str]:
    band = [TAPE]
    for index, symbol in enumerate(tape.cells):
        band.extend([CELL, HEAD if index == tape.head else NO_HEAD, *encode_symbol(encoding, symbol), END_CELL])
    return band + [END_TAPE]


def infer_minimal_abi(tm_program: TMProgram, source_band: TMBand, *, initial_state: str, halt_state: str) -> TMAbi:
    return infer_minimal_encoding_abi(
        tm_program,
        initial_state=initial_state,
        halt_state=halt_state,
        blank=source_band.blank,
        source_symbols=source_band.cells,
    )


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


def _target_abi_for_band(band: EncodedBand) -> TMAbi:
    return band.target_abi or abi_from_encoding(band.encoding)


def _minimal_abi_for_band(band: EncodedBand) -> TMAbi:
    return band.minimal_abi or _target_abi_for_band(band)


def utm_encoded_from_band(band: EncodedBand, *, minimal_abi: TMAbi | None = None) -> UTMEncoded:
    view = decoded_view_from_encoded_band(band)
    target_abi = _target_abi_for_band(band)
    return UTMEncoded(
        encoding=band.encoding,
        registers=view.registers,
        rules=view.rules,
        simulated_tape=view.simulated_tape,
        minimal_abi=_minimal_abi_for_band(band) if minimal_abi is None else minimal_abi,
        target_abi=target_abi,
    )


def utm_artifact_from_band(band: EncodedBand, *, minimal_abi: TMAbi | None = None) -> UTMBandArtifact:
    target_abi = _target_abi_for_band(band)
    return UTMBandArtifact(
        encoding=band.encoding,
        left_band=tuple(band.left_band),
        right_band=tuple(band.right_band),
        start_head=start_head_from_encoded_band(band),
        target_abi=target_abi,
        minimal_abi=_minimal_abi_for_band(band) if minimal_abi is None else minimal_abi,
    )


def encoded_band_from_utm_artifact(artifact: UTMBandArtifact) -> EncodedBand:
    return EncodedBand(
        artifact.encoding,
        list(artifact.left_band),
        list(artifact.right_band),
        minimal_abi=artifact.minimal_abi,
        target_abi=artifact.target_abi,
    )


__all__ = [
    "AbiRequirement",
    "DecodedBandView",
    "RawTMConfig",
    "TMRunConfig",
    "TMBand",
    "TMAbi",
    "TMInstance",
    "UTMEncoded",
    "UTMBandArtifact",
    "UTMEncodedRule",
    "UTMEncodingArtifact",
    "UTMRegisters",
    "UTMSimulatedTape",
    "abi_from_encoding",
    "decoded_view_from_encoded_band",
    "encoded_band_from_utm_artifact",
    "infer_minimal_abi",
    "source_band_from_simulated_tape",
    "start_head_from_encoded_band",
    "utm_artifact_from_band",
    "utm_encoded_from_band",
]
