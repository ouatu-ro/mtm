"""CFG model, compilation, validation, and assembly.

This layer receives Routine IR, expands its structured ops into CFGTransition
objects, validates the resulting graph, and finally assembles it into raw TM
transition rows. Read sets and write actions stay structured until assembly so
the CFG remains inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeAlias

from ..raw_transition_tm import TMBuilder
from .constants import Label, S, State, VALID_MOVES, move_for_direction
from .ops import BranchAtOp, BranchOnBitOp, EmitAllOp, EmitAnyExceptOp, EmitOp, MoveStepsOp, Op, SeekOp, SeekUntilOneOfOp, WriteBitOp
from .routines import NameSupply, Routine
from .source_map import CFGTransitionSource, RoutineSource, TransitionSourceMap, raw_transition_source, transition_source_from_op


@dataclass(frozen=True)
class ReadAny:
    """A transition that applies to every symbol in the alphabet."""

    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        return alphabet


@dataclass(frozen=True)
class ReadSymbol:
    """A transition that applies to exactly one symbol."""

    symbol: str

    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        del alphabet
        return (self.symbol,)


@dataclass(frozen=True)
class ReadSymbols:
    """A transition that applies to a fixed set of symbols."""

    symbols: frozenset[str]

    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(symbol for symbol in alphabet if symbol in self.symbols)


@dataclass(frozen=True)
class ReadAnyExcept:
    """A transition that applies to every symbol except a fixed set."""

    symbols: frozenset[str]

    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(symbol for symbol in alphabet if symbol not in self.symbols)


ReadSet: TypeAlias = ReadAny | ReadSymbol | ReadSymbols | ReadAnyExcept


@dataclass(frozen=True)
class KeepWrite:
    """Write action that leaves the read symbol unchanged."""

    def resolve(self, read: str) -> str:
        return read


@dataclass(frozen=True)
class WriteSymbolAction:
    """Write action that replaces the read symbol with one fixed symbol."""

    symbol: str

    def resolve(self, read: str) -> str:
        del read
        return self.symbol


WriteAction: TypeAlias = KeepWrite | WriteSymbolAction


@dataclass(frozen=True)
class CFGTransition:
    """One structured transition in a RoutineCFG.

    ``reads`` may represent many alphabet symbols. This keeps the CFG compact
    and inspectable until final assembly expands it.
    """

    source: State
    reads: ReadSet
    target: State
    write: WriteAction
    move: int
    source_meta: CFGTransitionSource | None = None


@dataclass(frozen=True)
class RoutineCFG:
    """Concrete control-flow graph for one Routine.

    Entry and exit labels have been resolved to concrete TM state names.
    Internal states are the states owned by this routine; exits are external
    targets such as the next block label or the halt state.
    """

    entry: State
    exits: tuple[State, ...]
    internal_states: tuple[State, ...]
    transitions: tuple[CFGTransition, ...]
    source: RoutineSource | None = None

    @property
    def states(self) -> tuple[State, ...]:
        return tuple(sorted(set(self.internal_states) | set(self.exits)))


class CFGCompiler:
    """Lower Routine ops into structured CFG transitions."""

    def __init__(self, *, names: NameSupply, halt_state: str):
        self.names = names
        self.halt_state = halt_state
        self.transitions: list[CFGTransition] = []

    def state(self, label: Label) -> State:
        """Resolve an external or routine-local label to a concrete state."""

        if label == "__HALT__":
            return self.halt_state
        if label.startswith("@"):
            return self.names.named(label)
        return label

    def fresh(self, hint: str) -> State:
        """Allocate a concrete internal state name."""

        return self.names.fresh(hint)

    def add(
        self,
        source: Label | State,
        reads: ReadSet,
        target: Label | State,
        write: WriteAction,
        move: int,
        *,
        source_meta: CFGTransitionSource | None = None,
    ) -> None:
        """Append one structured CFG transition."""

        self.transitions.append(CFGTransition(self.state(source), reads, self.state(target), write, move, source_meta))

    def compile_op(self, op: Op, *, source_meta: CFGTransitionSource | None = None) -> None:
        """Expand one Routine op into CFG transitions."""

        match op:
            case EmitOp(source, read, target, write, move):
                self.add(source, ReadSymbol(read), target, WriteSymbolAction(write), move, source_meta=source_meta)
            case EmitAllOp(source, target, move):
                self.add(source, ReadAny(), target, KeepWrite(), move, source_meta=source_meta)
            case SeekOp(source, target, markers, direction):
                move = move_for_direction(direction)
                self.add(source, ReadSymbols(markers), target, KeepWrite(), S, source_meta=source_meta)
                self.add(source, ReadAnyExcept(markers), source, KeepWrite(), move, source_meta=source_meta)
            case SeekUntilOneOfOp(source, found, boundary, found_target, boundary_target, direction):
                if not found:
                    raise ValueError("bounded seek requires at least one found marker")
                if not boundary:
                    raise ValueError("bounded seek requires at least one boundary marker")
                overlap = found & boundary
                if overlap:
                    raise ValueError(f"bounded seek markers cannot be both found and boundary: {sorted(overlap)!r}")
                move = move_for_direction(direction)
                self.add(source, ReadSymbols(found), found_target, KeepWrite(), S, source_meta=source_meta)
                self.add(source, ReadSymbols(boundary), boundary_target, KeepWrite(), S, source_meta=source_meta)
                self.add(source, ReadAnyExcept(found | boundary), source, KeepWrite(), move, source_meta=source_meta)
            case MoveStepsOp(source, target, steps, direction):
                if steps < 0:
                    raise ValueError(f"move steps must be non-negative: {steps!r}")
                if steps == 0:
                    self.add(source, ReadAny(), target, KeepWrite(), S, source_meta=source_meta)
                    return
                move = move_for_direction(direction)
                current = self.state(source)
                for index in range(steps):
                    next_state = self.state(target) if index + 1 == steps else self.fresh(f"{source}_move_{index}")
                    self.transitions.append(CFGTransition(current, ReadAny(), next_state, KeepWrite(), move, source_meta))
                    current = next_state
            case BranchOnBitOp(source, zero, one, move):
                self.add(source, ReadSymbol("0"), zero, KeepWrite(), move, source_meta=source_meta)
                self.add(source, ReadSymbol("1"), one, KeepWrite(), move, source_meta=source_meta)
            case WriteBitOp(source, target, bit, move):
                self.add(source, ReadSymbol("0"), target, WriteSymbolAction(bit), move, source_meta=source_meta)
                self.add(source, ReadSymbol("1"), target, WriteSymbolAction(bit), move, source_meta=source_meta)
            case BranchAtOp(source, marker, label_true, label_false):
                self.add(source, ReadSymbol(marker), label_true, KeepWrite(), S, source_meta=source_meta)
                self.add(source, ReadAnyExcept(frozenset({marker})), label_false, KeepWrite(), S, source_meta=source_meta)
            case EmitAnyExceptOp(source, except_symbol, target, move):
                self.add(source, ReadAnyExcept(frozenset({except_symbol})), target, KeepWrite(), move, source_meta=source_meta)

    def cfg(self, routine: Routine) -> RoutineCFG:
        """Build the immutable CFG for the compiled routine."""

        exits = tuple(self.state(exit_label) for exit_label in routine.exits)
        exit_set = set(exits)
        internal_states = {self.state(routine.entry)}
        for transition in self.transitions:
            internal_states.add(transition.source)
            if transition.target not in exit_set:
                internal_states.add(transition.target)
        return RoutineCFG(
            entry=self.state(routine.entry),
            exits=exits,
            internal_states=tuple(sorted(internal_states)),
            transitions=tuple(self.transitions),
            source=routine.source,
        )


def compile_routine(
    routine: Routine,
    names: NameSupply,
    *,
    halt_state: str = "U_HALT",
) -> RoutineCFG:
    """Compile one Routine into a structured CFG without mutating TMBuilder."""

    compiler = CFGCompiler(names=names, halt_state=halt_state)
    if routine.op_sources and len(routine.op_sources) != len(routine.ops):
        raise ValueError("routine op_sources must align 1:1 with ops")
    op_sources = routine.op_sources or (None,) * len(routine.ops)
    for op, op_source in zip(routine.ops, op_sources):
        compiler.compile_op(op, source_meta=transition_source_from_op(op_source))
    return compiler.cfg(routine)


def validate_cfg(cfg: RoutineCFG, alphabet: Iterable[str]) -> None:
    """Check CFG invariants before raw transition rows are emitted."""

    alphabet = tuple(alphabet)
    alphabet_set = set(alphabet)
    known_states = set(cfg.states)
    internal_states = set(cfg.internal_states)
    exit_states = set(cfg.exits)
    seen: set[tuple[str, str]] = set()
    outgoing: dict[str, set[str]] = {}

    if cfg.entry not in internal_states:
        raise ValueError(f"CFG entry must be an internal state: {cfg.entry!r}")
    overlapping_states = internal_states & exit_states
    if overlapping_states:
        raise ValueError(f"CFG states cannot be both internal and exits: {sorted(overlapping_states)!r}")
    exit_sources = exit_states & {transition.source for transition in cfg.transitions}
    if exit_sources:
        raise ValueError(f"CFG exit states have outgoing transitions: {sorted(exit_sources)!r}")

    for transition in cfg.transitions:
        if transition.source not in known_states:
            raise ValueError(f"unknown CFG transition source: {transition.source!r}")
        if transition.target not in known_states:
            raise ValueError(f"unknown CFG transition target: {transition.target!r}")
        if transition.move not in VALID_MOVES:
            raise ValueError(f"CFG transition has invalid move: {transition.move!r}")
        missing_read_refs = _explicit_read_symbols(transition.reads) - alphabet_set
        if missing_read_refs:
            raise ValueError(f"CFG transition reads symbols outside alphabet: {sorted(missing_read_refs)!r}")
        missing_write_refs = _explicit_write_symbols(transition.write) - alphabet_set
        if missing_write_refs:
            raise ValueError(f"CFG transition writes symbols outside alphabet: {sorted(missing_write_refs)!r}")
        reads = transition.reads.expand(alphabet)
        if not reads:
            raise ValueError(f"CFG transition has empty read set: {transition!r}")
        for read in reads:
            if read not in alphabet_set:
                raise ValueError(f"CFG transition reads symbol outside alphabet: {read!r}")
            write = transition.write.resolve(read)
            if write not in alphabet_set:
                raise ValueError(f"CFG transition writes symbol outside alphabet: {write!r}")
            key = (transition.source, read)
            if key in seen:
                raise ValueError(f"duplicate CFG transition for {key!r}")
            seen.add(key)
            outgoing.setdefault(transition.source, set()).add(transition.target)

    reachable = {cfg.entry}
    frontier = [cfg.entry]
    while frontier:
        state = frontier.pop()
        for target in outgoing.get(state, set()):
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)

    unreachable = {
        state
        for state in known_states
        if state not in reachable and any(transition.source == state for transition in cfg.transitions)
    }
    if unreachable:
        raise ValueError(f"unreachable CFG states: {sorted(unreachable)!r}")


def _explicit_read_symbols(reads: ReadSet) -> set[str]:
    match reads:
        case ReadSymbol(symbol):
            return {symbol}
        case ReadSymbols(symbols):
            return set(symbols)
        case ReadAnyExcept(symbols):
            return set(symbols)
        case ReadAny():
            return set()
        case _:
            raise TypeError(f"unsupported ReadSet: {reads!r}")


def _explicit_write_symbols(write: WriteAction) -> set[str]:
    match write:
        case WriteSymbolAction(symbol):
            return {symbol}
        case KeepWrite():
            return set()
        case _:
            raise TypeError(f"unsupported WriteAction: {write!r}")


def assemble_cfg(
    builder: TMBuilder,
    cfg: RoutineCFG,
    *,
    source_map: TransitionSourceMap | None = None,
) -> None:
    """Emit a validated RoutineCFG into a raw transition-machine builder."""

    for transition in cfg.transitions:
        for read in transition.reads.expand(builder.alphabet):
            builder.emit(
                transition.source,
                read,
                transition.target,
                transition.write.resolve(read),
                transition.move,
            )
            source = raw_transition_source(transition.source, read, transition.source_meta)
            if source_map is not None and source is not None:
                source_map.entries[(transition.source, read)] = source


__all__ = [
    "CFGCompiler",
    "CFGTransition",
    "KeepWrite",
    "ReadAny",
    "ReadAnyExcept",
    "ReadSet",
    "ReadSymbol",
    "ReadSymbols",
    "RoutineCFG",
    "WriteAction",
    "WriteSymbolAction",
    "assemble_cfg",
    "compile_routine",
    "validate_cfg",
]
