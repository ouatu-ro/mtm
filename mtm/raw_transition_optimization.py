"""Helpers for simplifying raw transition programs."""

from __future__ import annotations

from collections import defaultdict, deque

from .semantic_objects import RawTMInstance
from .raw_transition_tm import R, S
from .raw_transition_tm import TMTransitionProgram


def prune_unreachable_transitions(tm: TMTransitionProgram) -> TMTransitionProgram:
    """Return a copy of ``tm`` with transitions unreachable from ``start_state`` removed."""

    outgoing: dict[str, list[str]] = {}
    for (state, _), transition in tm.prog.items():
        outgoing.setdefault(state, []).append(transition[0])

    reachable = {tm.start_state}
    frontier = deque([tm.start_state])
    while frontier:
        state = frontier.popleft()
        for next_state in outgoing.get(state, ()):
            if next_state not in reachable:
                reachable.add(next_state)
                frontier.append(next_state)

    pruned_prog = {
        key: transition
        for key, transition in tm.prog.items()
        if key[0] in reachable
    }
    return TMTransitionProgram(
        pruned_prog,
        start_state=tm.start_state,
        halt_state=tm.halt_state,
        alphabet=tm.alphabet,
        blank=tm.blank,
    )


def find_identical_transition_state_classes(tm: TMTransitionProgram) -> list[tuple[str, ...]]:
    """Return duplicate state classes with identical full transition vectors."""

    states = _all_states(tm)
    by_signature: dict[tuple[tuple[str, str, int] | None, ...], list[str]] = defaultdict(list)
    for state in sorted(states):
        by_signature[_transition_signature(tm, state)].append(state)

    classes: list[tuple[str, ...]] = []
    for states in by_signature.values():
        if len(states) > 1:
            classes.append(tuple(states))
    return classes


def merge_identical_transition_states(tm: TMTransitionProgram) -> TMTransitionProgram:
    """Merge states whose complete transition vectors are identical."""

    classes = find_identical_transition_state_classes(tm)
    representative: dict[str, str] = {state: state for state in _all_states(tm)}

    for states in classes:
        if tm.halt_state in states and len(states) > 1:
            continue

        if tm.start_state in states:
            canonical = tm.start_state
        else:
            canonical = states[0]

        for state in states:
            representative[state] = canonical

    merged_prog: dict[tuple[str, str], tuple[str, str, int]] = {}
    for (state, read), (next_state, write, move) in tm.prog.items():
        canonical_state = representative[state]
        if canonical_state != state:
            continue
        merged_prog[(canonical_state, read)] = (representative.get(next_state, next_state), write, move)

    return TMTransitionProgram(
        merged_prog,
        start_state=tm.start_state,
        halt_state=tm.halt_state,
        alphabet=tm.alphabet,
        blank=tm.blank,
    )


def right_biased_raw_guest_state_order(instance: RawTMInstance, *, max_steps: int = 100_000) -> tuple[str, ...]:
    """Order states by the observed run, then by graph edges preferring right moves."""

    ordered: list[str] = []
    seen: set[str] = set()

    def add(state: str) -> None:
        if state not in seen:
            seen.add(state)
            ordered.append(state)

    tape = dict(instance.tape)
    head = instance.head
    state = instance.state
    for _step in range(max_steps):
        add(state)
        if state == instance.program.halt_state:
            break
        read = tape.get(head, instance.program.blank)
        transition = instance.program.transitions.get((state, read))
        if transition is None:
            break
        next_state, write, move = transition
        tape[head] = write
        head += move
        state = next_state
    add(instance.program.halt_state)

    outgoing: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for (source, read), (target, _write, move) in instance.program.transitions.items():
        outgoing[source].append((target, read, move))

    frontier = deque(ordered)
    while frontier:
        source = frontier.popleft()
        for target, _read, _move in sorted(outgoing.get(source, ()), key=_right_biased_edge_key):
            if target not in seen:
                add(target)
                frontier.append(target)

    for state in sorted(_all_states(instance.program)):
        add(state)
    return tuple(ordered)


def _right_biased_edge_key(edge: tuple[str, str, int]) -> tuple[int, str, str]:
    target, read, move = edge
    move_rank = {R: 0, S: 1}.get(move, 2)
    return (move_rank, read, target)


def _all_states(tm: TMTransitionProgram) -> set[str]:
    states = {tm.start_state, tm.halt_state}
    for (state, _), (next_state, _, _) in tm.prog.items():
        states.add(state)
        states.add(next_state)
    return states


def _transition_signature(tm: TMTransitionProgram, state: str) -> tuple[tuple[str, str, int] | None, ...]:
    return tuple(tm.prog.get((state, symbol)) for symbol in tm.alphabet)


__all__ = [
    "find_identical_transition_state_classes",
    "merge_identical_transition_states",
    "prune_unreachable_transitions",
    "right_biased_raw_guest_state_order",
]
