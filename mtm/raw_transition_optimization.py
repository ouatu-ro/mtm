"""Helpers for simplifying raw transition programs."""

from __future__ import annotations

from collections import deque

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


__all__ = ["prune_unreachable_transitions"]
