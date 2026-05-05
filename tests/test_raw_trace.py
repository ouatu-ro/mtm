from mtm import load_fixture
from mtm.debugger import RawTraceRunner
from mtm.lowering import lower_program_with_source_map
from mtm.lowering.constants import ACTIVE_RULE
from mtm.meta_asm import Block, Goto, Program, Seek, format_instruction
from mtm.raw_transition_tm import R, S, TMBuilder
from mtm.semantic_objects import start_head_from_encoded_band
from mtm.utm_band_layout import CUR_STATE, RULES
from mtm.meta_asm import build_universal_meta_asm


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


def test_raw_trace_grouped_routine_step_and_back_follow_source_boundaries() -> None:
    program = Program(
        blocks=(
            Block("ENTRY", (Seek(RULES, "R"), Goto("SECOND"))),
            Block("SECOND", (Goto("DONE"),)),
        ),
        entry_label="ENTRY",
    )
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(
        lowered.raw_program,
        {0: "0", 1: "0", 2: RULES},
        head=0,
        state="ENTRY",
        source_map=lowered.source_map,
    )

    forward = runner.step_to_next_routine()

    assert forward.status == "stepped"
    assert forward.raw_steps == 3
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "ENTRY"
    assert runner.current_transition_source.instruction_index == 1
    assert runner.current_transition_source.routine_name == "goto"

    backward = runner.back_to_previous_routine()

    assert backward.status == "stepped"
    assert backward.raw_steps == 3
    assert runner.current.state == "ENTRY"
    assert runner.current.head == 0
    assert runner.current.steps == 0
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.instruction_index == 0
    assert runner.current_transition_source.routine_name == "seek"


def test_raw_trace_grouped_instruction_step_and_back_follow_source_boundaries() -> None:
    program = Program(
        blocks=(Block("ENTRY", (Seek(RULES, "R"), Goto("DONE"))),),
        entry_label="ENTRY",
    )
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(
        lowered.raw_program,
        {0: "0", 1: "0", 2: RULES},
        head=0,
        state="ENTRY",
        source_map=lowered.source_map,
    )

    forward = runner.step_to_next_instruction()

    assert forward.status == "stepped"
    assert forward.raw_steps == 3
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.instruction_index == 1
    assert runner.current_transition_source.instruction == Goto("DONE")

    backward = runner.back_to_previous_instruction()

    assert backward.status == "stepped"
    assert backward.raw_steps == 3
    assert runner.current.state == "ENTRY"
    assert runner.current.steps == 0
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.instruction_index == 0
    assert runner.current_transition_source.instruction == Seek(RULES, "R")


def test_raw_trace_grouped_block_step_and_back_follow_source_boundaries() -> None:
    program = Program(
        blocks=(
            Block("ENTRY", (Seek(RULES, "R"), Goto("SECOND"))),
            Block("SECOND", (Seek(RULES, "L"), Goto("DONE"))),
        ),
        entry_label="ENTRY",
    )
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(
        lowered.raw_program,
        {0: "0", 1: "0", 2: RULES},
        head=0,
        state="ENTRY",
        source_map=lowered.source_map,
    )

    forward = runner.step_to_next_block()

    assert forward.status == "stepped"
    assert forward.raw_steps == 4
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "SECOND"
    assert runner.current_transition_source.instruction_index == 0

    backward = runner.back_to_previous_block()

    assert backward.status == "stepped"
    assert backward.raw_steps == 4
    assert runner.current.state == "ENTRY"
    assert runner.current.steps == 0
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "ENTRY"


def test_raw_trace_grouped_source_step_advances_to_next_utm_cycle_boundary() -> None:
    band = load_fixture("incrementer").build_band()
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        band.runtime_tape,
        head=start_head_from_encoded_band(band),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    forward = runner.step_to_next_source_step()

    assert forward.status == "stepped"
    assert forward.raw_steps > 0
    assert runner.current.steps == forward.raw_steps
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "START_STEP"
    assert runner.current.state == "START_STEP"


def test_raw_trace_grouped_source_step_back_rewinds_to_previous_utm_cycle_boundary() -> None:
    band = load_fixture("incrementer").build_band()
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        band.runtime_tape,
        head=start_head_from_encoded_band(band),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    first_boundary = runner.step_to_next_source_step()
    expected_tape = runner.current.tape_dict()
    expected_head = runner.current.head
    expected_state = runner.current.state
    expected_steps = runner.current.steps

    stepped = runner.step()
    backward = runner.back_to_previous_source_step()

    assert first_boundary.status == "stepped"
    assert stepped.status == "stepped"
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "START_STEP"
    assert runner.current.tape_dict() == expected_tape
    assert runner.current.head == expected_head
    assert runner.current.state == expected_state
    assert runner.current.steps == expected_steps
    assert backward.status == "stepped"
    assert backward.raw_steps == 1


def test_raw_trace_grouped_source_step_back_rewinds_to_initial_boundary() -> None:
    band = load_fixture("incrementer").build_band()
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        band.runtime_tape,
        head=start_head_from_encoded_band(band),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    runner.step()
    backward = runner.back_to_previous_source_step()

    assert backward.status == "stepped"
    assert backward.raw_steps == 1
    assert runner.current.steps == 0
    assert runner.current.state == "START_STEP"
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "START_STEP"


def test_raw_trace_current_view_projects_raw_and_decoded_state() -> None:
    band = load_fixture("incrementer").build_band()
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        band.runtime_tape,
        head=start_head_from_encoded_band(band),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    view = runner.current_view(encoding=band.encoding)

    assert view.snapshot == runner.current
    assert view.next_raw_transition_key == runner.current_transition_key
    assert view.next_raw_transition_row == runner.current_transition
    assert view.next_raw_transition_source == runner.current_transition_source
    assert view.last_transition is None
    assert view.last_transition_source is None
    assert view.decoded_view is not None
    assert view.decoded_view.current_state == "qFindMargin"
    assert view.decoded_view.simulated_head == 0
    assert view.decode_error is None


def test_raw_trace_current_view_reports_decode_error_for_incoherent_runtime_tape() -> None:
    band = load_fixture("incrementer").build_band()
    start_head = start_head_from_encoded_band(band)
    builder = TMBuilder(sorted(set(band.linear()) | {"0", "1"}), blank=band.encoding.blank)
    builder.emit("start", CUR_STATE, builder.halt_state, "0", S)
    runner = RawTraceRunner(builder.build("start"), band.runtime_tape, head=start_head)

    stepped = runner.step()
    view = runner.current_view(encoding=band.encoding)

    assert stepped.status == "stepped"
    assert view.decoded_view is None
    assert view.decode_error is not None
    assert "CUR_STATE" in view.decode_error
