"""Semantic objects for source machines and universal-machine artifacts.

The objects in this module are the teaching-facing model. They describe the
source Turing machine, the source tape, the encoded universal-machine input,
and the runnable universal-machine artifacts without exposing the incidental
layout mechanics first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .utm_band_layout import CELL, CMP_FLAG, CUR_STATE, CUR_SYMBOL, END_CELL, END_REGS, END_RULE, END_RULES, END_TAPE, END_TAPE_LEFT, HEAD, MOVE, MOVE_DIR, NEXT, NEXT_STATE, NO_HEAD, READ, REGS, RULE, RULES, STATE, TAPE, TAPE_LEFT, TMP, WRITE, WRITE_SYMBOL, EncodedBand, wrap_field
from .pretty import parse_left_tape, parse_registers, parse_rules, parse_tape
from .raw_transition_tm import TMTransitionProgram, run_raw_tm
from .source_encoding import Encoding, TMAbi, TMProgram, encode_direction, encode_state, encode_symbol, infer_minimal_abi as infer_minimal_encoding_abi


@dataclass(frozen=True, init=False)
class TMBand:
    """A source-machine tape with one head position.

    This is the tape seen by the object program being simulated. It is not the
    universal machine's encoded runtime tape.
    """

    right_band: tuple[str, ...]
    head: int
    blank: str
    left_band: tuple[str, ...]

    def __init__(
        self,
        right_band: tuple[str, ...] | None = None,
        *,
        head: int,
        blank: str,
        left_band: tuple[str, ...] = (),
        cells: tuple[str, ...] | None = None,
    ) -> None:
        if right_band is None:
            if cells is None:
                raise TypeError("TMBand requires right_band or cells")
            right_band = cells
        elif cells is not None:
            raise TypeError("TMBand accepts either right_band or cells, not both")
        left_band = tuple(left_band)
        right_band = tuple(right_band)
        if head < -len(left_band) or head >= len(right_band):
            raise ValueError("head outside source band")
        object.__setattr__(self, "left_band", left_band)
        object.__setattr__(self, "right_band", right_band)
        object.__setattr__(self, "head", head)
        object.__setattr__(self, "blank", blank)

    @classmethod
    def from_bands(
        cls,
        right_band: tuple[str, ...],
        *,
        head: int,
        blank: str,
        left_band: tuple[str, ...] = (),
    ) -> "TMBand":
        """Build a source tape from explicit negative and nonnegative sides."""

        return cls(right_band=right_band, left_band=left_band, head=head, blank=blank)

    @classmethod
    def from_dict(cls, cells: Mapping[int, str], *, head: int, blank: str) -> "TMBand":
        """Build a source tape from integer-addressed source cells."""

        if not cells:
            cells = {head: blank}
        low = min(min(cells), head, 0)
        high = max(max(cells), head, 0)
        left_band = tuple(cells.get(address, blank) for address in range(low, 0))
        right_band = tuple(cells.get(address, blank) for address in range(0, high + 1))
        return cls(right_band=right_band, left_band=left_band, head=head, blank=blank)

    @property
    def cells(self) -> tuple[str, ...]:
        """Return the finite source symbols used for ABI inference."""

        return self.left_band + self.right_band


@dataclass(frozen=True)
class TMInstance:
    """A complete source-machine input: program, tape, and optional states."""

    program: TMProgram
    band: TMBand
    initial_state: str | None = None
    halt_state: str | None = None


@dataclass(frozen=True)
class UTMRegisters:
    """Decoded register values used by the universal interpreter."""

    cur_state: str
    cur_symbol: str
    write_symbol: str
    next_state: str
    move_dir: int
    cmp_flag: str
    tmp_bits: tuple[str, ...]


@dataclass(frozen=True)
class UTMEncodedRule:
    """One source transition rule after decoding from the UTM rule table."""

    state: str
    read_symbol: str
    next_state: str
    write_symbol: str
    move_dir: int


@dataclass(frozen=True)
class UTMSimulatedTape:
    """Decoded object tape stored inside the universal-machine input."""

    right_band: tuple[str, ...]
    head: int
    blank: str
    left_band: tuple[str, ...] = ()

    @property
    def cells(self) -> tuple[str, ...]:
        """Return the finite decoded source symbols."""

        return self.left_band + self.right_band


@dataclass(frozen=True)
class UTMEncoded:
    """A source TM compiled into semantic universal-machine input.

    The object is still semantic: registers, rule records, and simulated tape
    are named fields. Use ``to_encoded_band`` or ``to_band_artifact`` when a
    concrete ``.utm.band`` layout is needed.
    """

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
        """Materialize this semantic object into the concrete band layout."""

        left_band = _left_tape_band_from_semantics(self.encoding, self.simulated_tape)
        left_band += _register_band_from_semantics(self.encoding, self.registers)
        left_band += _rule_band_from_semantics(self.encoding, self.rules)
        right_band = _right_tape_band_from_semantics(self.encoding, self.simulated_tape)
        return EncodedBand(
            self.encoding,
            left_band,
            right_band,
            minimal_abi=self.minimal_abi,
            target_abi=self.target_abi,
        )

    def to_band_artifact(self) -> "UTMBandArtifact":
        """Return the serializable ``.utm.band`` artifact object."""

        return utm_artifact_from_band(self.to_encoded_band(), minimal_abi=self.minimal_abi)

    def decoded_view(self) -> "DecodedBandView":
        """Return a decoded read-only view of this encoded UTM input."""

        return DecodedBandView(
            registers=self.registers,
            rules=self.rules,
            simulated_tape=self.simulated_tape,
            encoding=self.encoding,
        )


@dataclass(frozen=True)
class UTMBandArtifact:
    """Serializable universal-machine input artifact.

    This is the object form of a ``.utm.band`` file: left band, right band,
    start head, and the ABI metadata needed to decode it.
    """

    encoding: Encoding
    left_band: tuple[str, ...]
    right_band: tuple[str, ...]
    start_head: int
    target_abi: TMAbi
    minimal_abi: TMAbi

    def to_encoded_band(self) -> EncodedBand:
        """Convert this artifact to the lower-level encoded band layout."""

        return encoded_band_from_utm_artifact(self)

    def to_runtime_tape(self) -> dict[int, str]:
        """Materialize the left/right bands into a runtime tape dictionary."""

        return self.to_encoded_band().to_runtime_tape()

    def to_run_config(self, program_artifact: "UTMProgramArtifact | TMTransitionProgram") -> "TMRunConfig":
        """Pair this input artifact with a UTM program for raw execution."""

        program = program_artifact.program if isinstance(program_artifact, UTMProgramArtifact) else program_artifact
        return TMRunConfig(
            program=program,
            tape=self.to_runtime_tape(),
            head=self.start_head,
            state=program.start_state,
        )

    def write(self, path: str | "Path") -> None:
        from .artifacts import write_utm_artifact

        write_utm_artifact(path, self)

    @classmethod
    def read(cls, path: str | "Path") -> "UTMBandArtifact":
        from .artifacts import read_utm_artifact

        return read_utm_artifact(path)


@dataclass(frozen=True)
class TMRunConfig:
    """Runner-facing raw TM execution state."""

    program: TMTransitionProgram
    tape: dict[int, str]
    head: int
    state: str


@dataclass(frozen=True)
class UTMProgramArtifact:
    """Serializable universal-machine transition program artifact."""

    program: TMTransitionProgram
    target_abi: TMAbi | None = None
    minimal_abi: TMAbi | None = None

    def write(self, path: str | "Path") -> None:
        self.program.write(path)

    @classmethod
    def read(
        cls,
        path: str | "Path",
        *,
        target_abi: TMAbi | None = None,
        minimal_abi: TMAbi | None = None,
    ) -> "UTMProgramArtifact":
        return cls(
            program=TMTransitionProgram.read(path),
            target_abi=target_abi,
            minimal_abi=minimal_abi,
        )

    def run(self, band_artifact: UTMBandArtifact, *, fuel: int = 100) -> dict[str, object]:
        """Run this universal-machine program on a band artifact."""

        config = band_artifact.to_run_config(self)
        return run_raw_tm(
            config.program,
            config.tape,
            head=config.head,
            state=config.state,
            max_steps=fuel,
        )


@dataclass(frozen=True)
class DecodedBandView:
    """Decoded semantic view recovered from an encoded UTM band."""

    registers: UTMRegisters
    rules: tuple[UTMEncodedRule, ...]
    simulated_tape: UTMSimulatedTape
    encoding: Encoding

    @property
    def simulated_head(self) -> int: return self.simulated_tape.head

    @property
    def current_state(self) -> str: return self.registers.cur_state


def abi_from_encoding(encoding: Encoding) -> TMAbi:
    """Build ABI metadata from concrete encoding widths."""

    return TMAbi(
        state_width=encoding.state_width,
        symbol_width=encoding.symbol_width,
        dir_width=encoding.direction_width,
        family_label=f"U[Wq={encoding.state_width},Ws={encoding.symbol_width},Wd={encoding.direction_width}]",
    )


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


def _left_tape_band_from_semantics(encoding: Encoding, tape: UTMSimulatedTape) -> list[str]:
    band = [END_TAPE_LEFT]
    first_address = -len(tape.left_band)
    for index, symbol in enumerate(tape.left_band):
        address = first_address + index
        band.extend([CELL, HEAD if address == tape.head else NO_HEAD, *encode_symbol(encoding, symbol), END_CELL])
    return band + [TAPE_LEFT]


def _right_tape_band_from_semantics(encoding: Encoding, tape: UTMSimulatedTape) -> list[str]:
    band = [TAPE]
    for index, symbol in enumerate(tape.right_band):
        band.extend([CELL, HEAD if index == tape.head else NO_HEAD, *encode_symbol(encoding, symbol), END_CELL])
    return band + [END_TAPE]


def infer_minimal_abi(tm_program: TMProgram, source_band: TMBand, *, initial_state: str, halt_state: str) -> TMAbi:
    """Infer the smallest ABI that can encode a source program and band."""

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
    left_cells, left_head = parse_left_tape(band.encoding, band.left_band)
    right_cells, right_head = parse_tape(band.encoding, band.right_band, require_head=False)
    heads = [head for head in (left_head, right_head) if head is not None]
    if len(heads) != 1:
        raise ValueError("encoded UTM band must contain exactly one simulated head")
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
        simulated_tape=UTMSimulatedTape(
            left_band=tuple(left_cells),
            right_band=tuple(right_cells),
            head=heads[0],
            blank=band.encoding.blank,
        ),
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


__all__ = ["DecodedBandView", "TMRunConfig", "TMBand", "TMAbi", "TMInstance", "UTMEncoded", "UTMProgramArtifact",
           "UTMBandArtifact", "UTMEncodedRule", "UTMRegisters", "UTMSimulatedTape", "abi_from_encoding",
           "decoded_view_from_encoded_band", "encoded_band_from_utm_artifact", "infer_minimal_abi",
           "start_head_from_encoded_band", "utm_artifact_from_band", "utm_encoded_from_band"]
