from mtm.debugger import RawTraceRunner
from mtm.lowering import lower_program_with_source_map
from mtm.meta_asm import Block, Goto, Program, Seek, format_instruction
from mtm.raw_transition_tm import R, S, TMBuilder
from mtm.utm_band_layout import RULES


def test_raw_trace_step_executes_one_transition_and_exposes_next_row() -> None:
    builder = TMBuilder(["0", "1"])
    builder.emit("start", "0", "scan", "1", R)
    builder.emit("scan", "1", builder.halt_state, "1", S)
    runner = RawTraceRunner(builder.build("start"), {0: "0", 1: "1"}, head=0)

    step = runner.step()

    assert step.status == "stepped"
    assert step.transition is not None
    assert step.transition.state == "start"
    assert step.transition.read_symbol == "0"
    assert step.transition.write_symbol == "1"
    assert step.transition.next_state == "scan"
    assert step.transition.move == R
    assert runner.current.state == "scan"
    assert runner.current.head == 1
    assert runner.current.steps == 1
    assert runner.current.tape_dict() == {0: "1", 1: "1"}
    assert runner.current_transition_key == ("scan", "1")
    assert runner.current_transition == (builder.halt_state, "1", S)


def test_raw_trace_back_restores_previous_state_head_and_tape() -> None:
    builder = TMBuilder(["0", "1"])
    builder.emit("start", "0", "middle", "1", R)
    builder.emit("middle", "1", builder.halt_state, "0", S)
    runner = RawTraceRunner(builder.build("start"), {0: "0", 1: "1"}, head=0)

    runner.step()
    runner.step()

    assert runner.current.state == builder.halt_state
    assert runner.current.head == 1
    assert runner.current.tape_dict() == {0: "1", 1: "0"}
    assert runner.back() is True
    assert runner.current.state == "middle"
    assert runner.current.head == 1
    assert runner.current.steps == 1
    assert runner.current.tape_dict() == {0: "1", 1: "1"}
    assert runner.last_transition is not None
    assert runner.last_transition.state == "start"
    assert runner.back() is True
    assert runner.current.state == "start"
    assert runner.current.head == 0
    assert runner.current.steps == 0
    assert runner.current.tape_dict() == {0: "0", 1: "1"}
    assert runner.last_transition is None
    assert runner.back() is False


def test_raw_trace_run_reports_stuck_and_fuel_exhausted() -> None:
    stuck_builder = TMBuilder(["0"])
    stuck_runner = RawTraceRunner(stuck_builder.build("start"), {0: "0"}, head=0)

    stuck_result = stuck_runner.run(3)

    assert stuck_result.status == "stuck"
    assert stuck_result.steps_executed == 0
    assert stuck_runner.current.state == "start"
    assert stuck_runner.is_stuck is True

    loop_builder = TMBuilder(["0"])
    loop_builder.emit("start", "0", "start", "0", S)
    loop_runner = RawTraceRunner(loop_builder.build("start"), {0: "0"}, head=0)

    fuel_result = loop_runner.run(2)

    assert fuel_result.status == "fuel_exhausted"
    assert fuel_result.steps_executed == 2
    assert loop_runner.current.steps == 2
    assert loop_runner.current.state == "start"


def test_raw_trace_source_map_attaches_to_last_and_current_transition() -> None:
    instructions = (Seek(RULES, "L"), Goto("DONE"))
    lowered = lower_program_with_source_map(
        Program(blocks=(Block("ENTRY", instructions),), entry_label="ENTRY"),
        ("0", RULES),
    )
    seek_cfg, goto_cfg = lowered.cfgs
    runner = RawTraceRunner(
        lowered.raw_program,
        {0: RULES},
        head=0,
        state=seek_cfg.entry,
        source_map=lowered.source_map,
    )

    current_source = runner.current_transition_source
    step = runner.step()

    assert current_source is not None
    assert current_source.block_label == "ENTRY"
    assert current_source.instruction_index == 0
    assert current_source.instruction == instructions[0]
    assert current_source.instruction_text == format_instruction(instructions[0])
    assert step.transition is not None
    assert step.transition.source == current_source
    assert runner.last_transition_source == current_source

    next_source = runner.current_transition_source
    while next_source is not None and next_source.instruction_index == 0:
        runner.step()
        next_source = runner.current_transition_source

    assert next_source is not None
    assert next_source.block_label == "ENTRY"
    assert next_source.instruction_index == 1
    assert next_source.instruction == instructions[1]
    assert next_source.instruction_text == format_instruction(instructions[1])
    assert next_source.routine_index == 1
    assert next_source.routine_name == "goto"
    assert runner.current_transition_key == (next_source.state, next_source.read_symbol)
    assert next_source.state == goto_cfg.entry
