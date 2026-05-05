from mtm.raw_transition_optimization import prune_unreachable_transitions
from mtm.raw_transition_tm import R, S, TMBuilder


def test_prune_unreachable_transitions_keeps_only_reachable_component_and_metadata() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt", blank="_")
    builder.emit("start", "0", "mid", "0", R)
    builder.emit("mid", "1", "halt", "1", S)
    builder.emit("dead", "0", "dead", "0", R)
    builder.emit("dead", "1", "halt", "1", S)
    tm = builder.build("start")

    pruned = prune_unreachable_transitions(tm)

    assert pruned.start_state == "start"
    assert pruned.halt_state == "halt"
    assert pruned.blank == "_"
    assert pruned.alphabet == ("_", "0", "1")
    assert pruned.prog == {
        ("start", "0"): ("mid", "0", R),
        ("mid", "1"): ("halt", "1", S),
    }
    assert tm.prog != pruned.prog
