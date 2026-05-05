"""Lower Meta-ASM routines through an explicit CFG before raw TM emission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypeAlias

from .meta_asm import (
    Block,
    BranchAt,
    BranchCmp,
    CompareGlobalLiteral,
    CompareGlobalLocal,
    CopyGlobalGlobal,
    CopyGlobalToHeadSymbol,
    CopyHeadSymbolTo,
    CopyLocalGlobal,
    FindFirstRule,
    FindHeadCell,
    FindNextRule,
    Goto,
    Halt,
    Instruction,
    MoveSimHeadLeft,
    MoveSimHeadRight,
    Program,
    Seek,
    SeekOneOf,
    WriteGlobal,
)
from .raw_transition_tm import L, R, S, TMBuilder, TMTransitionProgram
from .utm_band_layout import (
    CELL,
    CMP_FLAG,
    CUR_STATE,
    CUR_SYMBOL,
    END_RULES,
    HEAD,
    MOVE_DIR,
    NEXT_STATE,
    NO_HEAD,
    REGS,
    RULE,
    RULES,
    TMP,
    WRITE_SYMBOL,
)

Label: TypeAlias = str
State: TypeAlias = str
Symbol: TypeAlias = str

GLOBAL_MARKERS = (CUR_STATE, CUR_SYMBOL, WRITE_SYMBOL, NEXT_STATE, MOVE_DIR, CMP_FLAG, TMP)
ACTIVE_RULE = "#ACTIVE_RULE"
VALID_MOVES = {L, S, R}


@dataclass(frozen=True)
class HeadAnywhere:
    pass


@dataclass(frozen=True)
class HeadOnRuntimeTape:
    pass


@dataclass(frozen=True)
class HeadAt:
    marker: str


@dataclass(frozen=True)
class HeadAtOneOf:
    markers: tuple[str, ...]


HeadContract: TypeAlias = HeadAnywhere | HeadOnRuntimeTape | HeadAt | HeadAtOneOf


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
Bit: TypeAlias = str
BIT_VALUES: tuple[Bit, Bit] = ("0", "1")


@dataclass(frozen=True)
class BitBranch:
    state: Label
    bit: Bit


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


@dataclass(frozen=True)
class EmitOp:
    source: Label
    read: Symbol
    target: Label
    write: Symbol
    move: int


@dataclass(frozen=True)
class EmitAllOp:
    source: Label
    target: Label
    move: int


@dataclass(frozen=True)
class SeekOp:
    source: Label
    target: Label
    markers: frozenset[str]
    direction: str


@dataclass(frozen=True)
class MoveStepsOp:
    source: Label
    target: Label
    steps: int
    direction: str


@dataclass(frozen=True)
class BranchOnBitOp:
    source: Label
    zero: Label
    one: Label
    move: int


@dataclass(frozen=True)
class WriteBitOp:
    source: Label
    target: Label
    bit: str
    move: int


@dataclass(frozen=True)
class BranchAtOp:
    source: Label
    marker: str
    label_true: Label
    label_false: Label


@dataclass(frozen=True)
class EmitAnyExceptOp:
    source: Label
    except_symbol: Symbol
    target: Label
    move: int


Op: TypeAlias = EmitOp | EmitAllOp | SeekOp | MoveStepsOp | BranchOnBitOp | WriteBitOp | BranchAtOp | EmitAnyExceptOp


@dataclass(frozen=True)
class Routine:
    name: str
    entry: Label
    exits: tuple[Label, ...]
    falls_through: bool
    ops: tuple[Op, ...]
    requires: HeadContract = HeadAnywhere()
    ensures: HeadContract = HeadAnywhere()


class NameSupply:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self._fresh_ids: dict[str, int] = {}
        self._named: dict[str, str] = {}

    def fresh(self, hint: str) -> str:
        clean_hint = hint.replace("@", "").replace("#", "").replace(" ", "_")
        next_id = self._fresh_ids.get(clean_hint, 0)
        self._fresh_ids[clean_hint] = next_id + 1
        return f"{self.prefix}_{clean_hint}_{next_id}"

    def named(self, local_label: str) -> str:
        if local_label not in self._named:
            clean_label = local_label.replace("@", "").replace("#", "").replace(" ", "_")
            self._named[local_label] = self.fresh(clean_label)
        return self._named[local_label]


class RoutineDraft:
    def __init__(
        self,
        name: str,
        *,
        entry: Label,
        exits: tuple[Label, ...],
        falls_through: bool = True,
        requires: HeadContract = HeadAnywhere(),
        ensures: HeadContract = HeadAnywhere(),
    ):
        self.name = name
        self.entry = entry
        self.exits = exits
        self.falls_through = falls_through
        self.requires = requires
        self.ensures = ensures
        self.ops: list[Op] = []
        self._local_ids: dict[str, int] = {}

    def local(self, hint: str) -> Label:
        next_id = self._local_ids.get(hint, 0)
        self._local_ids[hint] = next_id + 1
        return f"@{hint}_{next_id}"

    def add(self, op: Op) -> None:
        self.ops.append(op)

    def build(self) -> Routine:
        return Routine(
            name=self.name,
            entry=self.entry,
            exits=self.exits,
            falls_through=self.falls_through,
            ops=tuple(self.ops),
            requires=self.requires,
            ensures=self.ensures,
        )


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
                move = _move_for_direction(direction)
                self.add(source, ReadSymbols(markers), target, KeepWrite(), S)
                self.add(source, ReadAnyExcept(markers), source, KeepWrite(), move)
            case MoveStepsOp(source, target, steps, direction):
                if steps < 0:
                    raise ValueError(f"move steps must be non-negative: {steps!r}")
                if steps == 0:
                    self.add(source, ReadAny(), target, KeepWrite(), S)
                    return
                move = _move_for_direction(direction)
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


def _move_for_direction(direction: str) -> int:
    if direction == "R":
        return R
    if direction == "L":
        return L
    raise ValueError(f"unsupported direction: {direction!r}")


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


def global_direction(src_marker: str, dst_marker: str) -> str:
    return "R" if GLOBAL_MARKERS.index(src_marker) < GLOBAL_MARKERS.index(dst_marker) else "L"


def _seek(draft: RoutineDraft, source: Label, *, markers: set[str], direction: str, target: Label) -> None:
    draft.add(SeekOp(source, target, frozenset(markers), direction))


def _move_steps(draft: RoutineDraft, source: Label, *, steps: int, direction: str, target: Label) -> None:
    draft.add(MoveStepsOp(source, target, steps, direction))


def _branch_on_bit(draft: RoutineDraft, source: Label, *, zero_label: Label, one_label: Label, move: int) -> None:
    draft.add(BranchOnBitOp(source, zero_label, one_label, move))


def _branch_bit_at_offset(
    draft: RoutineDraft,
    source: Label,
    *,
    offset: int,
    move_after_read: int,
    prefix: str,
    index: int,
) -> tuple[BitBranch, BitBranch]:
    read_state = draft.local(f"{prefix}_read_{index}")
    zero_state = draft.local(f"{prefix}_bit0_{index}")
    one_state = draft.local(f"{prefix}_bit1_{index}")
    _move_steps(draft, source, steps=offset, direction="R", target=read_state)
    _branch_on_bit(draft, read_state, zero_label=zero_state, one_label=one_state, move=move_after_read)
    return (BitBranch(zero_state, "0"), BitBranch(one_state, "1"))


def _emit_expected_bit_branch(
    draft: RoutineDraft,
    source: Label,
    *,
    expected: Bit,
    match_target: Label,
    mismatch_target: Label,
    match_move: int,
    mismatch_move: int,
) -> None:
    if expected not in BIT_VALUES:
        raise ValueError(f"expected bit must be 0 or 1: {expected!r}")
    mismatch = "1" if expected == "0" else "0"
    draft.add(EmitOp(source, expected, match_target, expected, match_move))
    draft.add(EmitOp(source, mismatch, mismatch_target, mismatch, mismatch_move))


def _write_current_bit(draft: RoutineDraft, source: Label, *, bit: str, target: Label, move: int) -> None:
    draft.add(WriteBitOp(source, target, bit, move))


def _write_bit_at_offset(
    draft: RoutineDraft,
    source: Label,
    *,
    bit: Bit,
    offset: int,
    target: Label,
    write_move: int,
    prefix: str,
    index: int,
) -> None:
    write_state = draft.local(f"{prefix}_write_{bit}_{index}")
    _move_steps(draft, source, steps=offset, direction="R", target=write_state)
    _write_current_bit(draft, write_state, bit=bit, target=target, move=write_move)


def _seek_then_write_bit_at_offset(
    draft: RoutineDraft,
    source: Label,
    *,
    marker: str,
    seek_direction: str,
    bit: Bit,
    offset: int,
    target: Label,
    write_move: int,
    prefix: str,
    index: int,
) -> None:
    marker_state = draft.local(f"{prefix}_marker_{bit}_{index}")
    _seek(draft, source, markers={marker}, direction=seek_direction, target=marker_state)
    _write_bit_at_offset(
        draft,
        marker_state,
        bit=bit,
        offset=offset,
        target=target,
        write_move=write_move,
        prefix=prefix,
        index=index,
    )


def _seek_active_rule(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    _seek(draft, source, markers={ACTIVE_RULE}, direction="R", target=target)


def _activate_rule_at_head(draft: RoutineDraft, source: Label, *, target: Label) -> None:
    draft.add(EmitOp(source, RULE, target, ACTIVE_RULE, S))
    draft.add(EmitOp(source, ACTIVE_RULE, target, ACTIVE_RULE, S))


def _write_cmp_flag(draft: RoutineDraft, source: Label, *, bit: str, target: Label) -> None:
    write_state = draft.local("write_cmp_flag")
    draft.add(EmitOp(source, CMP_FLAG, write_state, CMP_FLAG, R))
    _write_current_bit(draft, write_state, bit=bit, target=target, move=L)


def _halt_routine(state: Label, cont: Label) -> Routine:
    del cont
    draft = RoutineDraft("halt", entry=state, exits=("__HALT__",), falls_through=False)
    draft.add(EmitAllOp(state, "__HALT__", S))
    return draft.build()


def _goto_routine(state: Label, cont: Label, label: Label) -> Routine:
    del cont
    draft = RoutineDraft("goto", entry=state, exits=(label,), falls_through=False)
    draft.add(EmitAllOp(state, label, S))
    return draft.build()


def _seek_routine(state: Label, cont: Label, marker: str, direction: str) -> Routine:
    draft = RoutineDraft("seek", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAt(marker))
    _seek(draft, state, markers={marker}, direction=direction, target=cont)
    return draft.build()


def _seek_one_of_routine(state: Label, cont: Label, markers: tuple[str, ...], direction: str) -> Routine:
    draft = RoutineDraft("seek_one_of", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAtOneOf(markers))
    _seek(draft, state, markers=set(markers), direction=direction, target=cont)
    return draft.build()


def _find_first_rule_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("find_first_rule", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAtOneOf((RULE, END_RULES)))
    seek_regs = draft.local("seek_regs")
    seek_rules = draft.local("seek_rules")
    seek_rule = draft.local("seek_rule")
    mark_rule = draft.local("mark_rule")
    draft.add(EmitAllOp(state, seek_regs, S))
    _seek(draft, seek_regs, markers={REGS}, direction="L", target=seek_rules)
    _seek(draft, seek_rules, markers={RULES}, direction="R", target=seek_rule)
    _seek(draft, seek_rule, markers={RULE, END_RULES}, direction="R", target=mark_rule)
    draft.add(EmitOp(mark_rule, RULE, cont, ACTIVE_RULE, S))
    draft.add(EmitOp(mark_rule, END_RULES, cont, END_RULES, S))
    return draft.build()


def _find_next_rule_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("find_next_rule", entry=state, exits=(cont,), requires=HeadAtOneOf((RULE, ACTIVE_RULE)), ensures=HeadAtOneOf((RULE, END_RULES)))
    seek_next = draft.local("seek_next")
    mark_rule = draft.local("mark_rule")
    draft.add(EmitOp(state, ACTIVE_RULE, seek_next, RULE, R))
    draft.add(EmitOp(state, RULE, seek_next, RULE, R))
    _seek(draft, seek_next, markers={RULE, END_RULES}, direction="R", target=mark_rule)
    draft.add(EmitOp(mark_rule, RULE, cont, ACTIVE_RULE, S))
    draft.add(EmitOp(mark_rule, END_RULES, cont, END_RULES, S))
    return draft.build()


def _find_head_cell_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("find_head_cell", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAt(CELL))
    scan_cell = draft.local("scan")
    inspect_flag = draft.local("flag")
    return_cell = draft.local("return")
    draft.add(EmitAllOp(state, scan_cell, S))
    draft.add(EmitOp(scan_cell, CELL, inspect_flag, CELL, R))
    draft.add(EmitAnyExceptOp(scan_cell, CELL, scan_cell, R))
    draft.add(EmitOp(inspect_flag, HEAD, return_cell, HEAD, L))
    draft.add(EmitAnyExceptOp(inspect_flag, HEAD, scan_cell, R))
    draft.add(EmitOp(return_cell, CELL, cont, CELL, S))
    return draft.build()


def _move_sim_head_right_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("move_sim_head_right", entry=state, exits=(cont,), requires=HeadAt(CELL), ensures=HeadAt(CELL))
    clear_flag = draft.local("clear_flag")
    scan_next = draft.local("scan_next")
    mark_head = draft.local("mark_head")
    draft.add(EmitOp(state, CELL, clear_flag, CELL, R))
    draft.add(EmitOp(clear_flag, HEAD, scan_next, NO_HEAD, R))
    draft.add(EmitOp(clear_flag, NO_HEAD, scan_next, NO_HEAD, R))
    draft.add(EmitOp(scan_next, CELL, mark_head, CELL, R))
    draft.add(EmitAnyExceptOp(scan_next, CELL, scan_next, R))
    draft.add(EmitOp(mark_head, HEAD, cont, HEAD, L))
    draft.add(EmitOp(mark_head, NO_HEAD, cont, HEAD, L))
    return draft.build()


def _move_sim_head_left_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("move_sim_head_left", entry=state, exits=(cont,), requires=HeadAt(CELL), ensures=HeadAt(CELL))
    clear_flag = draft.local("clear_flag")
    leave_current = draft.local("leave_current")
    scan_prev = draft.local("scan_prev")
    mark_head = draft.local("mark_head")
    draft.add(EmitOp(state, CELL, clear_flag, CELL, R))
    draft.add(EmitOp(clear_flag, HEAD, leave_current, NO_HEAD, L))
    draft.add(EmitOp(clear_flag, NO_HEAD, leave_current, NO_HEAD, L))
    draft.add(EmitOp(leave_current, CELL, scan_prev, CELL, L))
    draft.add(EmitOp(scan_prev, CELL, mark_head, CELL, R))
    draft.add(EmitAnyExceptOp(scan_prev, CELL, scan_prev, L))
    draft.add(EmitOp(mark_head, HEAD, cont, HEAD, L))
    draft.add(EmitOp(mark_head, NO_HEAD, cont, HEAD, L))
    return draft.build()


def _deactivate_active_rule_routine(state: Label, cont: Label) -> Routine:
    draft = RoutineDraft("deactivate_active_rule", entry=state, exits=(cont,), requires=HeadAtOneOf((ACTIVE_RULE, RULE)), ensures=HeadAt(RULE))
    draft.add(EmitOp(state, ACTIVE_RULE, cont, RULE, S))
    draft.add(EmitOp(state, RULE, cont, RULE, S))
    return draft.build()


def _copy_global_global_routine(state: Label, cont: Label, src_marker: str, dst_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_global_global", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadOnRuntimeTape())
    to_dst, to_src = global_direction(src_marker, dst_marker), global_direction(dst_marker, src_marker)
    current = draft.local("seek_src")
    seek_regs = draft.local("seek_regs")
    _seek(draft, state, markers={REGS}, direction="L", target=seek_regs)
    _seek(draft, seek_regs, markers={src_marker}, direction="R", target=current)
    for index in range(width):
        branches = _branch_bit_at_offset(
            draft,
            current,
            offset=index + 1,
            move_after_read=R if to_dst == "R" else L,
            prefix="src",
            index=index,
        )
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            if index + 1 == width:
                _seek_then_write_bit_at_offset(
                    draft,
                    branch.state,
                    marker=dst_marker,
                    seek_direction=to_dst,
                    bit=branch.bit,
                    offset=index + 1,
                    target=cont,
                    write_move=S,
                    prefix="dst",
                    index=index,
                )
            else:
                back_to_src = draft.local(f"back_to_src_{branch.bit}_{index}")
                _seek_then_write_bit_at_offset(
                    draft,
                    branch.state,
                    marker=dst_marker,
                    seek_direction=to_dst,
                    bit=branch.bit,
                    offset=index + 1,
                    target=back_to_src,
                    write_move=R if to_src == "R" else L,
                    prefix="dst",
                    index=index,
                )
                _seek(draft, back_to_src, markers={src_marker}, direction=to_src, target=next_iter)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _copy_local_global_routine(state: Label, cont: Label, local_marker: str, global_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_local_global", entry=state, exits=(cont,), requires=HeadAtOneOf((RULE, ACTIVE_RULE)), ensures=HeadAt(ACTIVE_RULE))
    activate_rule = draft.local("activate_rule")
    current = activate_rule
    _activate_rule_at_head(draft, state, target=activate_rule)
    for index in range(width):
        local_marker_state = draft.local(f"local_marker_{index}")
        _seek(draft, current, markers={local_marker}, direction="R", target=local_marker_state)
        branches = _branch_bit_at_offset(
            draft,
            local_marker_state,
            offset=index + 1,
            move_after_read=L,
            prefix="local",
            index=index,
        )
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            back_to_rule = draft.local(f"back_to_rule_{branch.bit}_{index}")
            _seek_then_write_bit_at_offset(
                draft,
                branch.state,
                marker=global_marker,
                seek_direction="L",
                bit=branch.bit,
                offset=index + 1,
                target=back_to_rule,
                write_move=S,
                prefix="global",
                index=index,
            )
            _seek_active_rule(draft, back_to_rule, target=cont if index + 1 == width else next_iter)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _copy_head_symbol_to_routine(state: Label, cont: Label, global_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_head_symbol_to", entry=state, exits=(cont,), requires=HeadAt(CELL), ensures=HeadOnRuntimeTape())
    current = state
    for index in range(width):
        branches = _branch_bit_at_offset(
            draft,
            current,
            offset=index + 2,
            move_after_read=L,
            prefix="head",
            index=index,
        )
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            if index + 1 == width:
                _seek_then_write_bit_at_offset(
                    draft,
                    branch.state,
                    marker=global_marker,
                    seek_direction="L",
                    bit=branch.bit,
                    offset=index + 1,
                    target=cont,
                    write_move=S,
                    prefix="global",
                    index=index,
                )
            else:
                back_to_head = draft.local(f"back_to_head_{branch.bit}_{index}")
                back_to_cell = draft.local(f"back_to_cell_{branch.bit}_{index}")
                _seek_then_write_bit_at_offset(
                    draft,
                    branch.state,
                    marker=global_marker,
                    seek_direction="L",
                    bit=branch.bit,
                    offset=index + 1,
                    target=back_to_head,
                    write_move=S,
                    prefix="global",
                    index=index,
                )
                _seek(draft, back_to_head, markers={HEAD}, direction="R", target=back_to_cell)
                draft.add(EmitOp(back_to_cell, HEAD, next_iter, HEAD, L))
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _copy_global_to_head_symbol_routine(state: Label, cont: Label, global_marker: str, width: int) -> Routine:
    draft = RoutineDraft("copy_global_to_head_symbol", entry=state, exits=(cont,), requires=HeadAt(CELL), ensures=HeadOnRuntimeTape())
    current = state
    for index in range(width):
        global_marker_state = draft.local(f"global_marker_{index}")
        _seek(draft, current, markers={global_marker}, direction="L", target=global_marker_state)
        branches = _branch_bit_at_offset(
            draft,
            global_marker_state,
            offset=index + 1,
            move_after_read=R,
            prefix="global",
            index=index,
        )
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            head_flag_state = draft.local(f"head_flag_{branch.bit}_{index}")
            cell_state = draft.local(f"cell_state_{branch.bit}_{index}")
            _seek(draft, branch.state, markers={HEAD}, direction="R", target=head_flag_state)
            draft.add(EmitOp(head_flag_state, HEAD, cell_state, HEAD, L))
            if index + 1 == width:
                _write_bit_at_offset(
                    draft,
                    cell_state,
                    bit=branch.bit,
                    offset=index + 2,
                    target=cont,
                    write_move=S,
                    prefix="head",
                    index=index,
                )
            else:
                back_to_cell = draft.local(f"back_to_cell_{branch.bit}_{index}")
                _write_bit_at_offset(
                    draft,
                    cell_state,
                    bit=branch.bit,
                    offset=index + 2,
                    target=back_to_cell,
                    write_move=L,
                    prefix="head",
                    index=index,
                )
                _seek(draft, back_to_cell, markers={CELL}, direction="L", target=next_iter)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _compare_global_literal_routine(state: Label, cont: Label, global_marker: str, literal_bits: tuple[str, ...]) -> Routine:
    draft = RoutineDraft("compare_global_literal", entry=state, exits=(cont,), requires=HeadOnRuntimeTape(), ensures=HeadAt(CMP_FLAG))
    dir_to_cmp = global_direction(global_marker, CMP_FLAG)
    seek_regs = draft.local("seek_regs")
    marker_state = draft.local("marker")
    current = draft.local("read_0")
    _seek(draft, state, markers={REGS}, direction="L", target=seek_regs)
    _seek(draft, seek_regs, markers={global_marker}, direction="R", target=marker_state)
    draft.add(EmitOp(marker_state, global_marker, current, global_marker, R))
    for index, expected in enumerate(literal_bits):
        next_read = draft.local(f"read_{index + 1}") if index + 1 < len(literal_bits) else None
        seek_false = draft.local(f"seek_false_{index}")
        seek_true = draft.local(f"seek_true_{index}") if next_read is None else None
        expected_target = next_read if next_read else seek_true
        expected_move = R if next_read else (R if dir_to_cmp == "R" else L)
        mismatch_move = R if dir_to_cmp == "R" else L
        _emit_expected_bit_branch(
            draft,
            current,
            expected=expected,
            match_target=expected_target,
            mismatch_target=seek_false,
            match_move=expected_move,
            mismatch_move=mismatch_move,
        )
        cmp_false_state = draft.local(f"false_cmp_{index}")
        _seek(draft, seek_false, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_false_state)
        if seek_true is not None:
            cmp_true_state = draft.local(f"true_cmp_{index}")
            _seek(draft, seek_true, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_true_state)
            _write_cmp_flag(draft, cmp_true_state, bit="1", target=cont)
        _write_cmp_flag(draft, cmp_false_state, bit="0", target=cont)
        current = next_read if next_read else current
    return draft.build()


def _compare_global_local_routine(state: Label, cont: Label, global_marker: str, local_marker: str, width: int) -> Routine:
    draft = RoutineDraft("compare_global_local", entry=state, exits=(cont,), requires=HeadAtOneOf((RULE, ACTIVE_RULE)), ensures=HeadAt(ACTIVE_RULE))
    dir_to_cmp = global_direction(global_marker, CMP_FLAG)
    activate_rule = draft.local("activate_rule")
    current = activate_rule
    _activate_rule_at_head(draft, state, target=activate_rule)
    for index in range(width):
        local_marker_state = draft.local(f"local_marker_{index}")
        _seek(draft, current, markers={local_marker}, direction="R", target=local_marker_state)
        branches = _branch_bit_at_offset(
            draft,
            local_marker_state,
            offset=index + 1,
            move_after_read=L,
            prefix="local",
            index=index,
        )
        next_iter = draft.local(f"next_{index}") if index + 1 < width else None
        for branch in branches:
            global_marker_state = draft.local(f"global_marker_{branch.bit}_{index}")
            _seek(draft, branch.state, markers={global_marker}, direction="L", target=global_marker_state)
            global_read = draft.local(f"global_read_{branch.bit}_{index}")
            _move_steps(draft, global_marker_state, steps=index + 1, direction="R", target=global_read)
            mismatch_bit = "1" if branch.bit == "0" else "0"
            mismatch_seek = draft.local(f"mismatch_seek_{branch.bit}_{index}")
            draft.add(EmitOp(global_read, mismatch_bit, mismatch_seek, mismatch_bit, S))
            cmp_false_state = draft.local(f"false_cmp_{branch.bit}_{index}")
            after_false = draft.local(f"after_false_{branch.bit}_{index}")
            _seek(draft, mismatch_seek, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_false_state)
            _write_cmp_flag(draft, cmp_false_state, bit="0", target=after_false)
            _seek_active_rule(draft, after_false, target=cont)
            if next_iter is not None:
                back_to_rule = draft.local(f"back_to_rule_{branch.bit}_{index}")
                draft.add(EmitOp(global_read, branch.bit, back_to_rule, branch.bit, S))
                _seek_active_rule(draft, back_to_rule, target=next_iter)
            else:
                match_seek = draft.local(f"match_seek_{branch.bit}_{index}")
                cmp_true_state = draft.local(f"true_cmp_{branch.bit}_{index}")
                after_true = draft.local(f"after_true_{branch.bit}_{index}")
                draft.add(EmitOp(global_read, branch.bit, match_seek, branch.bit, S))
                _seek(draft, match_seek, markers={CMP_FLAG}, direction=dir_to_cmp, target=cmp_true_state)
                _write_cmp_flag(draft, cmp_true_state, bit="1", target=after_true)
                _seek_active_rule(draft, after_true, target=cont)
        if next_iter is not None:
            current = next_iter
    return draft.build()


def _branch_cmp_routine(state: Label, cont: Label, label_equal: Label, label_not_equal: Label) -> Routine:
    del cont
    draft = RoutineDraft(
        "branch_cmp",
        entry=state,
        exits=(label_equal, label_not_equal),
        falls_through=False,
        requires=HeadAtOneOf((CMP_FLAG, ACTIVE_RULE)),
        ensures=HeadOnRuntimeTape(),
    )
    active_seek_cmp = draft.local("active_seek_cmp")
    active_read_cmp = draft.local("active_read_cmp")
    active_bit = draft.local("active_bit")
    active_seek_eq = draft.local("active_seek_eq")
    active_seek_neq = draft.local("active_seek_neq")
    draft.add(EmitOp(state, ACTIVE_RULE, active_seek_cmp, ACTIVE_RULE, L))
    _seek(draft, active_seek_cmp, markers={CMP_FLAG}, direction="L", target=active_read_cmp)
    draft.add(EmitOp(active_read_cmp, CMP_FLAG, active_bit, CMP_FLAG, R))
    draft.add(EmitOp(active_bit, "1", active_seek_eq, "1", L))
    draft.add(EmitOp(active_bit, "0", active_seek_neq, "0", L))
    _seek(draft, active_seek_eq, markers={ACTIVE_RULE}, direction="R", target=label_equal)
    _seek(draft, active_seek_neq, markers={ACTIVE_RULE}, direction="R", target=label_not_equal)
    read_cmp = draft.local("read")
    draft.add(EmitOp(state, CMP_FLAG, read_cmp, CMP_FLAG, R))
    draft.add(EmitOp(read_cmp, "1", label_equal, "1", S))
    draft.add(EmitOp(read_cmp, "0", label_not_equal, "0", S))
    return draft.build()


def _write_global_routine(state: Label, cont: Label, global_marker: str, literal_bits: tuple[str, ...]) -> Routine:
    draft = RoutineDraft("write_global", entry=state, exits=(cont,), requires=HeadAt(global_marker), ensures=HeadOnRuntimeTape())
    bit_states = [draft.local(f"bit_{index}") for index in range(len(literal_bits))]
    draft.add(EmitOp(state, global_marker, bit_states[0] if bit_states else cont, global_marker, R if bit_states else S))
    for index, bit in enumerate(literal_bits):
        next_state = bit_states[index + 1] if index + 1 < len(bit_states) else cont
        _write_current_bit(draft, bit_states[index], bit=bit, target=next_state, move=R if index + 1 < len(bit_states) else S)
    return draft.build()


def lower_instruction_to_routine(instruction: Instruction, *, state: Label, cont: Label) -> Routine:
    match instruction:
        case Halt():
            return _halt_routine(state, cont)
        case Goto(label):
            return _goto_routine(state, cont, label)
        case Seek(marker, direction):
            return _seek_routine(state, cont, marker, direction)
        case SeekOneOf(markers, direction):
            return _seek_one_of_routine(state, cont, markers, direction)
        case FindFirstRule():
            return _find_first_rule_routine(state, cont)
        case FindNextRule():
            return _find_next_rule_routine(state, cont)
        case FindHeadCell():
            return _find_head_cell_routine(state, cont)
        case BranchAt(marker, label_true, label_false):
            del cont
            draft = RoutineDraft(
                "branch_at",
                entry=state,
                exits=(label_true, label_false),
                falls_through=False,
                requires=HeadOnRuntimeTape(),
                ensures=HeadOnRuntimeTape(),
            )
            draft.add(BranchAtOp(state, marker, label_true, label_false))
            return draft.build()
        case BranchCmp(label_equal, label_not_equal):
            return _branch_cmp_routine(state, cont, label_equal, label_not_equal)
        case CompareGlobalLiteral(global_marker, literal_bits):
            return _compare_global_literal_routine(state, cont, global_marker, literal_bits)
        case CompareGlobalLocal(global_marker, local_marker, width):
            return _compare_global_local_routine(state, cont, global_marker, local_marker, width)
        case CopyGlobalGlobal(src_marker, dst_marker, width):
            return _copy_global_global_routine(state, cont, src_marker, dst_marker, width)
        case CopyLocalGlobal(local_marker, global_marker, width):
            return _copy_local_global_routine(state, cont, local_marker, global_marker, width)
        case CopyHeadSymbolTo(global_marker, width):
            return _copy_head_symbol_to_routine(state, cont, global_marker, width)
        case CopyGlobalToHeadSymbol(global_marker, width):
            return _copy_global_to_head_symbol_routine(state, cont, global_marker, width)
        case WriteGlobal(global_marker, literal_bits):
            return _write_global_routine(state, cont, global_marker, literal_bits)
        case MoveSimHeadLeft():
            return _move_sim_head_left_routine(state, cont)
        case MoveSimHeadRight():
            return _move_sim_head_right_routine(state, cont)
        case _:
            raise NotImplementedError(f"lowering not implemented for {instruction!r}")


def block_entry_setup(block: Block) -> Instruction | None:
    if block.label == "START_STEP":
        return Seek(CUR_STATE, "L")
    if block.label == "LOOKUP_RULE":
        return SeekOneOf((ACTIVE_RULE, END_RULES), "R")
    if block.label in {"CHECK_STATE", "CHECK_READ", "NEXT_RULE", "MATCHED_RULE"}:
        return Seek(ACTIVE_RULE, "R")
    if block.label in {"DISPATCH_MOVE", "CHECK_RIGHT"}:
        return Seek(MOVE_DIR, "L")
    return None


def instruction_sequence_to_routines(
    instructions: tuple[Instruction, ...] | list[Instruction],
    *,
    start_state: Label,
    exit_label: Label,
    names: NameSupply,
) -> tuple[Routine, ...]:
    routines: list[Routine] = []
    current_state = start_state
    instructions = tuple(instructions)
    for index, instruction in enumerate(instructions):
        cont = exit_label if index + 1 == len(instructions) else names.fresh(f"{start_state}_cont_{index}")
        routine = lower_instruction_to_routine(instruction, state=current_state, cont=cont)
        if not routine.falls_through and index + 1 < len(instructions):
            raise ValueError(f"terminal instruction before end of block: {instruction!r}")
        routines.append(routine)
        current_state = cont
    return tuple(routines)


def block_to_routines(block: Block, names: NameSupply) -> tuple[Routine, ...]:
    routines: list[Routine] = []
    start_state = block.label
    setup = block_entry_setup(block)
    body_start = start_state
    if setup is not None:
        body_start = names.fresh(f"{block.label}_body")
        routines.append(lower_instruction_to_routine(setup, state=start_state, cont=body_start))
    if block.label != "MATCHED_RULE":
        routines.extend(
            instruction_sequence_to_routines(
                block.instructions,
                start_state=body_start,
                exit_label=names.fresh(f"{block.label}_exit"),
                names=names,
            )
        )
        return tuple(routines)

    copied_fields = names.fresh("matched_rule_copied_fields")
    resume = names.fresh("matched_rule_resume")
    routines.extend(
        instruction_sequence_to_routines(
            block.instructions[:3],
            start_state=body_start,
            exit_label=copied_fields,
            names=names,
        )
    )
    routines.append(_deactivate_active_rule_routine(copied_fields, resume))
    routines.extend(
        instruction_sequence_to_routines(
            block.instructions[3:],
            start_state=resume,
            exit_label=names.fresh("MATCHED_RULE_exit"),
            names=names,
        )
    )
    return tuple(routines)


def program_to_routines(program: Program, names: NameSupply | None = None) -> tuple[Routine, ...]:
    names = NameSupply("program") if names is None else names
    routines: list[Routine] = []
    for block in program.blocks:
        routines.extend(block_to_routines(block, names))
    return tuple(routines)


def program_to_cfgs(program: Program, *, halt_state: str = "U_HALT") -> tuple[RoutineCFG, ...]:
    program_names = NameSupply("program")
    cfgs: list[RoutineCFG] = []
    for index, routine in enumerate(program_to_routines(program, program_names)):
        cfgs.append(
            compile_routine(
                routine,
                NameSupply(f"routine_{index}_{routine.name}"),
                halt_state=halt_state,
            )
        )
    return tuple(cfgs)


def validate_program_cfgs(cfgs: tuple[RoutineCFG, ...], alphabet: Iterable[str]) -> None:
    alphabet = tuple(alphabet)
    seen: dict[tuple[str, str], int] = {}
    for cfg_index, cfg in enumerate(cfgs):
        validate_cfg(cfg, alphabet)
        for transition in cfg.transitions:
            for read in transition.reads.expand(alphabet):
                key = (transition.source, read)
                if key in seen:
                    raise ValueError(
                        f"duplicate program CFG transition for {key!r} "
                        f"in routine CFG {cfg_index}; first seen in routine CFG {seen[key]}"
                    )
                seen[key] = cfg_index


def assemble_program(builder: TMBuilder, program: Program) -> None:
    cfgs = program_to_cfgs(program, halt_state=builder.halt_state)
    validate_program_cfgs(cfgs, builder.alphabet)
    for cfg in cfgs:
        assemble_cfg(builder, cfg)


def lower_program_to_raw_tm(
    program: Program,
    alphabet: Iterable[str],
    *,
    halt_state: str = "U_HALT",
    blank: str = "_RUNTIME_BLANK",
) -> TMTransitionProgram:
    builder = TMBuilder([*alphabet, ACTIVE_RULE], halt_state=halt_state, blank=blank)
    assemble_program(builder, program)
    return builder.build(program.entry_label)


__all__ = [
    "ACTIVE_RULE",
    "BranchAtOp",
    "BranchOnBitOp",
    "CFGTransition",
    "EmitAllOp",
    "EmitAnyExceptOp",
    "EmitOp",
    "HeadAnywhere",
    "HeadAt",
    "HeadAtOneOf",
    "HeadOnRuntimeTape",
    "KeepWrite",
    "MoveStepsOp",
    "NameSupply",
    "ReadAny",
    "ReadAnyExcept",
    "ReadSet",
    "ReadSymbol",
    "ReadSymbols",
    "Routine",
    "RoutineCFG",
    "SeekOp",
    "WriteAction",
    "WriteBitOp",
    "WriteSymbolAction",
    "assemble_cfg",
    "assemble_program",
    "block_to_routines",
    "compile_routine",
    "global_direction",
    "instruction_sequence_to_routines",
    "lower_instruction_to_routine",
    "lower_program_to_raw_tm",
    "program_to_routines",
    "program_to_cfgs",
    "validate_cfg",
    "validate_program_cfgs",
]
