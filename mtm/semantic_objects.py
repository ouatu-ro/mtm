"""Semantic objects for source machines and universal-machine artifacts.

The objects in this module are the teaching-facing model. They describe the
source Turing machine, the source tape, the encoded universal-machine input,
and the runnable universal-machine artifacts without exposing the incidental
layout mechanics first.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Mapping

from .utm_band_layout import BLANK_SYMBOL, CELL, CMP_FLAG, CUR_STATE, CUR_SYMBOL, END_CELL, END_REGS, END_RULE, END_RULES, END_TAPE, END_TAPE_LEFT, HALT_STATE, HEAD, LEFT_DIR, MOVE, MOVE_DIR, NEXT, NEXT_STATE, NO_HEAD, READ, REGS, RIGHT_DIR, RULE, RULES, STATE, TAPE, TAPE_LEFT, TMP, WRITE, WRITE_SYMBOL, EncodedBand, wrap_field
from .pretty import parse_left_tape, parse_registers, parse_rules, parse_tape
from .raw_transition_tm import L as RAW_L, R as RAW_R, S as RAW_S, TMTransitionProgram, run_raw_tm
from .source_encoding import Encoding, TMAbi, TMProgram, assert_abi_compatible, assert_host_abi_supports_band, assign_ids, encode_direction, encode_state, encode_symbol, infer_minimal_abi as infer_minimal_encoding_abi, width_for


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
class SourceArtifact:
    """Serializable source-level TM input artifact."""

    program: TMProgram
    band: TMBand
    initial_state: str
    halt_state: str
    name: str | None = None
    note: str | None = None

    def to_instance(self) -> TMInstance:
        """Return the compiler-facing source instance."""

        return TMInstance(
            program=self.program,
            band=self.band,
            initial_state=self.initial_state,
            halt_state=self.halt_state,
        )

    def write(self, path: str | "Path") -> None:
        from .artifacts import write_source_artifact

        write_source_artifact(path, self)

    @classmethod
    def read(cls, path: str | "Path") -> "SourceArtifact":
        from .artifacts import read_source_artifact

        return read_source_artifact(path)


@dataclass(frozen=True)
class UTMRegisters:
    """Decoded register values used by the universal interpreter."""

    cur_state: str
    cur_symbol: str
    write_symbol: str
    next_state: str
    move_dir: int
    halt_state: str
    blank_symbol: str
    left_dir: int
    right_dir: int
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

    def to_raw_instance(self, program_artifact: "UTMProgramArtifact | TMTransitionProgram") -> "RawTMInstance":
        """Pair this input artifact with a raw program instance."""

        program = program_artifact.program if isinstance(program_artifact, UTMProgramArtifact) else program_artifact
        return RawTMInstance(
            program=program,
            tape=self.to_runtime_tape(),
            head=self.start_head,
            state=program.start_state,
        )

    def to_run_config(self, program_artifact: "UTMProgramArtifact | TMTransitionProgram") -> "RawTMInstance":
        """Backward-compatible alias for ``to_raw_instance``."""

        return self.to_raw_instance(program_artifact)

    def write(self, path: str | "Path") -> None:
        from .artifacts import write_utm_artifact

        write_utm_artifact(path, self)

    @classmethod
    def read(cls, path: str | "Path") -> "UTMBandArtifact":
        from .artifacts import read_utm_artifact

        return read_utm_artifact(path)


@dataclass(frozen=True)
class RawTMInstance:
    """A raw transition program paired with its current tape/head/state."""

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
        from .artifacts import write_utm_program_artifact

        write_utm_program_artifact(path, self)

    @classmethod
    def read(cls, path: str | "Path") -> "UTMProgramArtifact":
        from .artifacts import read_utm_program_artifact

        return read_utm_program_artifact(path)

    def run(self, band_artifact: UTMBandArtifact, *, fuel: int = 100) -> dict[str, object]:
        """Run this universal-machine program on a band artifact."""

        if self.target_abi is not None and band_artifact.target_abi is not None:
            assert_host_abi_supports_band(self.target_abi, band_artifact.target_abi)
        config = band_artifact.to_raw_instance(self)
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
        *wrap_field(HALT_STATE, encode_state(encoding, registers.halt_state)),
        *wrap_field(BLANK_SYMBOL, encode_symbol(encoding, registers.blank_symbol)),
        *wrap_field(LEFT_DIR, encode_direction(encoding, registers.left_dir)),
        *wrap_field(RIGHT_DIR, encode_direction(encoding, registers.right_dir)),
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


def _raw_guest_states(instance: RawTMInstance, *, state_order: Iterable[str] = ()) -> list[str]:
    states = {instance.program.start_state, instance.program.halt_state, instance.state}
    for (state, _read_symbol), (next_state, _write_symbol, _move_direction) in instance.program.transitions.items():
        states.update((state, next_state))
    ordered = [state for state in dict.fromkeys(state_order) if state in states]
    ordered_set = set(ordered)
    return [*ordered, *(state for state in sorted(states) if state not in ordered_set)]


def _assign_state_ids(states: list[str], *, width: int, scatter: bool = False) -> dict[str, int]:
    if not scatter:
        return assign_ids(states)
    return {
        state: _reverse_low_bits(index, width)
        for index, state in enumerate(states)
    }


def _reverse_low_bits(value: int, width: int) -> int:
    reversed_value = 0
    for _index in range(width):
        reversed_value = (reversed_value << 1) | (value & 1)
        value >>= 1
    return reversed_value


def _raw_guest_symbols(instance: RawTMInstance) -> list[str]:
    symbols = {instance.program.blank, *instance.program.alphabet, *instance.tape.values()}
    for (_state, read_symbol), (_next_state, write_symbol, _move_direction) in instance.program.transitions.items():
        symbols.update((read_symbol, write_symbol))
    return [instance.program.blank, *(symbol for symbol in sorted(symbols) if symbol != instance.program.blank)]


def _raw_guest_directions(instance: RawTMInstance) -> list[int]:
    directions = {RAW_L, RAW_R}
    for _transition_key, (_next_state, _write_symbol, move_direction) in instance.program.transitions.items():
        if move_direction not in {RAW_L, RAW_S, RAW_R}:
            raise ValueError(f"unsupported raw move direction {move_direction!r}; expected L, S, or R")
        directions.add(move_direction)
    return [direction for direction in (RAW_L, RAW_R, RAW_S) if direction in directions]


def _raw_guest_tape(instance: RawTMInstance) -> UTMSimulatedTape:
    cells = dict(instance.tape)
    if not cells:
        cells = {instance.head: instance.program.blank}
    low = min(min(cells), instance.head, 0)
    high = max(max(cells), instance.head, 0)
    return UTMSimulatedTape(
        left_band=tuple(cells.get(address, instance.program.blank) for address in range(low, 0)),
        right_band=tuple(cells.get(address, instance.program.blank) for address in range(0, high + 1)),
        head=instance.head,
        blank=instance.program.blank,
    )


def infer_raw_guest_minimal_abi(instance: RawTMInstance) -> TMAbi:
    """Infer the smallest ABI needed to encode a raw guest instance."""

    state_width = width_for(len(_raw_guest_states(instance)))
    symbol_width = width_for(len(_raw_guest_symbols(instance)))
    dir_width = width_for(len(_raw_guest_directions(instance)))
    return TMAbi(
        state_width=state_width,
        symbol_width=symbol_width,
        dir_width=dir_width,
        family_label=f"raw-min[Wq={state_width},Ws={symbol_width},Wd={dir_width}]",
    )


def _validate_raw_guest_abi(required: TMAbi, abi: TMAbi) -> None:
    errors = []
    if abi.grammar_version != required.grammar_version:
        errors.append(f"grammar_version requires {required.grammar_version!r}, ABI provides {abi.grammar_version!r}")
    if required.state_width > abi.state_width:
        errors.append(f"states require {required.state_width} bits, ABI provides {abi.state_width}")
    if required.symbol_width > abi.symbol_width:
        errors.append(f"symbols require {required.symbol_width} bits, ABI provides {abi.symbol_width}")
    if required.dir_width > abi.dir_width:
        errors.append(f"directions require {required.dir_width} bits, ABI provides {abi.dir_width}")
    if errors:
        if any(error.startswith(("states", "symbols", "directions")) for error in errors):
            raise ValueError("selected ABI too small: " + "; ".join(errors))
        raise ValueError("selected ABI incompatible: " + "; ".join(errors))


def build_raw_guest_encoding(
    instance: RawTMInstance,
    *,
    abi: TMAbi | None = None,
    state_order: Iterable[str] = (),
    scatter_state_ids: bool = False,
) -> Encoding:
    """Build a concrete encoding for an already-lowered raw guest."""

    required = infer_raw_guest_minimal_abi(instance)
    target = required if abi is None else abi
    if abi is not None:
        _validate_raw_guest_abi(required, abi)
    states = _raw_guest_states(instance, state_order=state_order)
    return Encoding(
        state_ids=_assign_state_ids(states, width=target.state_width, scatter=scatter_state_ids),
        symbol_ids=assign_ids(_raw_guest_symbols(instance)),
        direction_ids=assign_ids(_raw_guest_directions(instance)),
        state_width=target.state_width,
        symbol_width=target.symbol_width,
        direction_width=target.dir_width,
        blank=instance.program.blank,
        initial_state=instance.state,
        halt_state=instance.program.halt_state,
    )


def _raw_guest_transition_items(
    instance: RawTMInstance,
    *,
    state_order: Iterable[str] = (),
):
    items = tuple(instance.program.transitions.items())
    state_rank = {state: index for index, state in enumerate(state_order)}
    if not state_rank:
        return items
    original_rank = {item: index for index, item in enumerate(items)}
    return tuple(sorted(
        items,
        key=lambda item: (
            state_rank.get(item[0][0], len(state_rank)),
            original_rank[item],
        ),
    ))


def compile_raw_guest(
    instance: RawTMInstance,
    *,
    abi: TMAbi | None = None,
    state_order: Iterable[str] = (),
    scatter_state_ids: bool = False,
) -> UTMEncoded:
    """Compile an already-lowered raw guest into semantic UTM input."""

    minimal_abi = infer_raw_guest_minimal_abi(instance)
    target_abi = minimal_abi if abi is None else abi
    state_order = tuple(state_order)
    encoding = build_raw_guest_encoding(
        instance,
        abi=target_abi,
        state_order=state_order,
        scatter_state_ids=scatter_state_ids,
    )
    simulated_tape = _raw_guest_tape(instance)
    return UTMEncoded(
        encoding=encoding,
        registers=UTMRegisters(
            cur_state=instance.state,
            cur_symbol=instance.program.blank,
            write_symbol=instance.program.blank,
            next_state=instance.state,
            move_dir=RAW_L,
            halt_state=instance.program.halt_state,
            blank_symbol=instance.program.blank,
            left_dir=RAW_L,
            right_dir=RAW_R,
            cmp_flag="0",
            tmp_bits=("0",) * max(encoding.state_width, encoding.symbol_width, encoding.direction_width),
        ),
        rules=tuple(
            UTMEncodedRule(
                state=state,
                read_symbol=read_symbol,
                next_state=next_state,
                write_symbol=write_symbol,
                move_dir=move_direction,
            )
            for (state, read_symbol), (next_state, write_symbol, move_direction) in _raw_guest_transition_items(
                instance,
                state_order=state_order,
            )
        ),
        simulated_tape=simulated_tape,
        minimal_abi=minimal_abi,
        target_abi=target_abi,
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
            halt_state=registers["HALT_STATE"],
            blank_symbol=registers["BLANK_SYMBOL"],
            left_dir=registers["LEFT_DIR"],
            right_dir=registers["RIGHT_DIR"],
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


__all__ = ["DecodedBandView", "RawTMInstance", "SourceArtifact", "TMBand", "TMAbi", "TMInstance", "UTMEncoded", "UTMProgramArtifact",
           "UTMBandArtifact", "UTMEncodedRule", "UTMRegisters", "UTMSimulatedTape", "abi_from_encoding",
           "build_raw_guest_encoding", "compile_raw_guest", "decoded_view_from_encoded_band", "encoded_band_from_utm_artifact",
           "infer_minimal_abi", "infer_raw_guest_minimal_abi", "start_head_from_encoded_band",
           "utm_artifact_from_band", "utm_encoded_from_band"]
