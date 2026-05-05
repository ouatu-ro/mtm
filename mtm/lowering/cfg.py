"""Routine CFG compilation, validation, and raw TM assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeAlias

from ..raw_transition_tm import TMBuilder
from .constants import Label, S, State, VALID_MOVES, move_for_direction
from .ops import BranchAtOp, BranchOnBitOp, EmitAllOp, EmitAnyExceptOp, EmitOp, MoveStepsOp, Op, SeekOp, WriteBitOp
from .routines import NameSupply, Routine


@dataclass(frozen=True)
class ReadAny:
    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        return alphabet


@dataclass(frozen=True)
class ReadSymbol:
    symbol: str

    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        del alphabet
        return (self.symbol,)


@dataclass(frozen=True)
class ReadSymbols:
    symbols: frozenset[str]

    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(symbol for symbol in alphabet if symbol in self.symbols)


@dataclass(frozen=True)
class ReadAnyExcept:
    symbols: frozenset[str]

    def expand(self, alphabet: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(symbol for symbol in alphabet if symbol not in self.symbols)


ReadSet: TypeAlias = ReadAny | ReadSymbol | ReadSymbols | ReadAnyExcept


@dataclass(frozen=True)
class KeepWrite:
    def resolve(self, read: str) -> str:
        return read


@dataclass(frozen=True)
class WriteSymbolAction:
    symbol: str

    def resolve(self, read: str) -> str:
        del read
        return self.symbol


WriteAction: TypeAlias = KeepWrite | WriteSymbolAction


@dataclass(frozen=True)
class CFGTransition:
    source: State
    reads: ReadSet
    target: State
    write: WriteAction
    move: int


@dataclass(frozen=True)
class RoutineCFG:
    entry: State
    exits: tuple[State, ...]
    internal_states: tuple[State, ...]
    transitions: tuple[CFGTransition, ...]

    @property
    def states(self) -> tuple[State, ...]:
        return tuple(sorted(set(self.internal_states) | set(self.exits)))


class CFGCompiler:
    def __init__(self, *, names: NameSupply, halt_state: str):
        self.names = names
        self.halt_state = halt_state
        self.transitions: list[CFGTransition] = []

    def state(self, label: Label) -> State:
        if label == "__HALT__":
            return self.halt_state
        if label.startswith("@"):
            return self.names.named(label)
        return label

    def fresh(self, hint: str) -> State:
        return self.names.fresh(hint)

    def add(self, source: Label | State, reads: ReadSet, target: Label | State, write: WriteAction, move: int) -> None:
        self.transitions.append(CFGTransition(self.state(source), reads, self.state(target), write, move))

    def compile_op(self, op: Op) -> None:
        match op:
            case EmitOp(source, read, target, write, move):
                self.add(source, ReadSymbol(read), target, WriteSymbolAction(write), move)
            case EmitAllOp(source, target, move):
                self.add(source, ReadAny(), target, KeepWrite(), move)
            case SeekOp(source, target, markers, direction):
                move = move_for_direction(direction)
                self.add(source, ReadSymbols(markers), target, KeepWrite(), S)
                self.add(source, ReadAnyExcept(markers), source, KeepWrite(), move)
            case MoveStepsOp(source, target, steps, direction):
                if steps < 0:
                    raise ValueError(f"move steps must be non-negative: {steps!r}")
                if steps == 0:
                    self.add(source, ReadAny(), target, KeepWrite(), S)
                    return
                move = move_for_direction(direction)
                current = self.state(source)
                for index in range(steps):
                    next_state = self.state(target) if index + 1 == steps else self.fresh(f"{source}_move_{index}")
                    self.transitions.append(CFGTransition(current, ReadAny(), next_state, KeepWrite(), move))
                    current = next_state
            case BranchOnBitOp(source, zero, one, move):
                self.add(source, ReadSymbol("0"), zero, KeepWrite(), move)
                self.add(source, ReadSymbol("1"), one, KeepWrite(), move)
            case WriteBitOp(source, target, bit, move):
                self.add(source, ReadSymbol("0"), target, WriteSymbolAction(bit), move)
                self.add(source, ReadSymbol("1"), target, WriteSymbolAction(bit), move)
            case BranchAtOp(source, marker, label_true, label_false):
                self.add(source, ReadSymbol(marker), label_true, KeepWrite(), S)
                self.add(source, ReadAnyExcept(frozenset({marker})), label_false, KeepWrite(), S)
            case EmitAnyExceptOp(source, except_symbol, target, move):
                self.add(source, ReadAnyExcept(frozenset({except_symbol})), target, KeepWrite(), move)

    def cfg(self, routine: Routine) -> RoutineCFG:
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
        )


def compile_routine(
    routine: Routine,
    names: NameSupply,
    *,
    halt_state: str = "U_HALT",
) -> RoutineCFG:
    compiler = CFGCompiler(names=names, halt_state=halt_state)
    for op in routine.ops:
        compiler.compile_op(op)
    return compiler.cfg(routine)


def validate_cfg(cfg: RoutineCFG, alphabet: Iterable[str]) -> None:
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


def assemble_cfg(builder: TMBuilder, cfg: RoutineCFG) -> None:
    for transition in cfg.transitions:
        for read in transition.reads.expand(builder.alphabet):
            builder.emit(
                transition.source,
                read,
                transition.target,
                transition.write.resolve(read),
                transition.move,
            )


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
