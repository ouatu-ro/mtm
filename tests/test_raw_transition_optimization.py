from mtm.raw_transition_optimization import (
    find_identical_transition_state_classes,
    merge_identical_transition_states,
    prune_unreachable_transitions,
    right_biased_raw_guest_state_order,
)
from mtm.raw_transition_tm import L, R, S, TMBuilder
from mtm.semantic_objects import RawTMInstance, compile_raw_guest


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


def test_merge_identical_transition_states_keeps_start_state_canonical_and_redirects_inbound_references() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt", blank="_")
    builder.emit("start", "0", "mid", "0", R)
    builder.emit("start", "1", "halt", "1", S)
    builder.emit("alias", "0", "mid", "0", R)
    builder.emit("alias", "1", "halt", "1", S)
    builder.emit("mid", "0", "halt", "0", S)
    builder.emit("mid", "1", "halt", "1", S)
    builder.emit("observer", "0", "alias", "0", S)
    builder.emit("observer", "1", "halt", "1", S)
    tm = builder.build("start")

    assert find_identical_transition_state_classes(tm) == [("alias", "start")]

    merged = merge_identical_transition_states(tm)

    assert merged.start_state == "start"
    assert merged.halt_state == "halt"
    assert merged.blank == "_"
    assert merged.alphabet == ("_", "0", "1")
    assert merged.prog == {
        ("start", "0"): ("mid", "0", R),
        ("start", "1"): ("halt", "1", S),
        ("mid", "0"): ("halt", "0", S),
        ("mid", "1"): ("halt", "1", S),
        ("observer", "0"): ("start", "0", S),
        ("observer", "1"): ("halt", "1", S),
    }


def test_merge_identical_transition_states_does_not_merge_stuck_states_into_halt() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt", blank="_")
    builder.emit("start", "0", "halt_clone", "0", S)
    builder.emit("start", "1", "halt", "1", S)
    builder.emit("observer", "0", "halt_clone", "0", S)
    builder.emit("observer", "1", "observer", "1", S)
    tm = builder.build("start")

    merged = merge_identical_transition_states(tm)

    assert merged.start_state == "start"
    assert merged.halt_state == "halt"
    assert merged.prog == {
        ("start", "0"): ("halt_clone", "0", S),
        ("start", "1"): ("halt", "1", S),
        ("observer", "0"): ("halt_clone", "0", S),
        ("observer", "1"): ("observer", "1", S),
    }


def test_prune_then_merge_identical_transition_states_composes_cleanly() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt", blank="_")
    builder.emit("start", "0", "mid", "0", R)
    builder.emit("start", "1", "halt", "1", S)
    builder.emit("alias", "0", "mid", "0", R)
    builder.emit("alias", "1", "halt", "1", S)
    builder.emit("mid", "0", "halt", "0", S)
    builder.emit("mid", "1", "halt", "1", S)
    builder.emit("dead", "0", "dead", "0", R)
    builder.emit("dead", "1", "dead", "1", R)
    builder.emit("dead_alias", "0", "dead", "0", R)
    builder.emit("dead_alias", "1", "dead", "1", R)
    tm = builder.build("start")

    merged = merge_identical_transition_states(prune_unreachable_transitions(tm))

    assert merged.prog == {
        ("start", "0"): ("mid", "0", R),
        ("start", "1"): ("halt", "1", S),
        ("mid", "0"): ("halt", "0", S),
        ("mid", "1"): ("halt", "1", S),
    }


def test_right_biased_raw_guest_state_order_prefers_observed_then_right_edges() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt", blank="_")
    builder.emit("start", "0", "left_branch", "0", L)
    builder.emit("start", "1", "right_branch", "1", R)
    builder.emit("right_branch", "_", "halt", "_", S)
    builder.emit("left_branch", "_", "halt", "_", S)
    tm = builder.build("start")
    instance = RawTMInstance(program=tm, tape={0: "1"}, head=0, state="start")

    assert right_biased_raw_guest_state_order(instance) == ("start", "right_branch", "halt", "left_branch")


def test_compile_raw_guest_can_use_state_order_for_ids_and_rule_layout() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt", blank="_")
    builder.emit("start", "0", "left_branch", "0", L)
    builder.emit("start", "1", "right_branch", "1", R)
    builder.emit("left_branch", "_", "halt", "_", S)
    builder.emit("right_branch", "_", "halt", "_", S)
    tm = builder.build("start")
    instance = RawTMInstance(program=tm, tape={0: "1"}, head=0, state="start")
    state_order = right_biased_raw_guest_state_order(instance)

    encoded = compile_raw_guest(instance, state_order=state_order)

    assert list(encoded.encoding.state_ids) == ["start", "right_branch", "halt", "left_branch"]
    assert [rule.state for rule in encoded.rules] == ["start", "start", "right_branch", "left_branch"]


def test_compile_raw_guest_can_scatter_ordered_state_ids() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt", blank="_")
    builder.emit("start", "0", "left_branch", "0", L)
    builder.emit("start", "1", "right_branch", "1", R)
    builder.emit("left_branch", "_", "halt", "_", S)
    builder.emit("right_branch", "_", "halt", "_", S)
    tm = builder.build("start")
    instance = RawTMInstance(program=tm, tape={0: "1"}, head=0, state="start")
    state_order = right_biased_raw_guest_state_order(instance)

    encoded = compile_raw_guest(instance, state_order=state_order, scatter_state_ids=True)

    assert encoded.encoding.state_width == 2
    assert encoded.encoding.state_ids == {
        "start": 0,
        "right_branch": 2,
        "halt": 1,
        "left_branch": 3,
    }
