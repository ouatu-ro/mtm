from mtm import load_fixture
from mtm.debugger import RawTraceRunner, format_group_step_result, format_source_location, format_trace_view
from mtm.lowering import lower_program_with_source_map
from mtm.lowering.constants import ACTIVE_RULE
from mtm.meta_asm import Block, Goto, Program, Seek, format_instruction
from mtm.raw_transition_tm import R, S, TMBuilder
from mtm.semantic_objects import start_head_from_encoded_tape
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


def test_raw_trace_stream_step_keeps_only_current_snapshot() -> None:
    builder = TMBuilder(["0", "1"])
    builder.emit("start", "0", "middle", "1", R)
    builder.emit("middle", "1", builder.halt_state, "0", S)
    runner = RawTraceRunner(builder.build("start"), {0: "0", 1: "1"}, head=0)

    first = runner.stream_step()
    second = runner.stream_step()

    assert first.status == "stepped"
    assert first.transition is not None
    assert first.transition.state == "start"
    assert second.status == "stepped"
    assert second.transition is not None
    assert second.transition.state == "middle"
    assert runner.current.state == builder.halt_state
    assert runner.current.head == 1
    assert runner.current.steps == 2
    assert runner.current.tape_dict() == {0: "1", 1: "0"}
    assert runner.history_cursor == 0
    assert runner.latest_history_index == 0
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


def test_raw_trace_stream_instruction_step_keeps_source_boundary_without_history() -> None:
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

    forward = runner.stream_to_next_instruction()

    assert forward.status == "stepped"
    assert forward.raw_steps == 3
    assert runner.current.steps == 3
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "ENTRY"
    assert runner.current_transition_source.instruction_index == 1
    assert runner.current_transition_source.routine_name == "goto"
    assert runner.history_cursor == 0
    assert runner.latest_history_index == 0
    assert runner.back() is False


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
    assert forward.raw_steps > 0
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
    assert forward.raw_steps > 0
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
    assert forward.raw_steps > 0
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
    tape = load_fixture("incrementer").build_encoded_tape()
    program = build_universal_meta_asm(tape.encoding)
    alphabet = sorted(set(tape.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        tape.runtime_tape,
        head=start_head_from_encoded_tape(tape),
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
    tape = load_fixture("incrementer").build_encoded_tape()
    program = build_universal_meta_asm(tape.encoding)
    alphabet = sorted(set(tape.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        tape.runtime_tape,
        head=start_head_from_encoded_tape(tape),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    first_boundary_start = runner.step_to_next_source_step()
    source_step_zero = runner.current.steps
    second_boundary_start = runner.step_to_next_source_step()
    source_step_one = runner.current.steps
    third_boundary_start = runner.step_to_next_source_step()
    source_step_two = runner.current.steps

    assert first_boundary_start.status == "stepped"
    assert second_boundary_start.status == "stepped"
    assert third_boundary_start.status == "stepped"
    assert source_step_two > source_step_one > source_step_zero

    backward = runner.back_to_previous_source_step()
    assert backward.status == "stepped"
    assert backward.raw_steps == source_step_two - source_step_one
    assert runner.current.steps == source_step_one
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "START_STEP"

    backward = runner.back_to_previous_source_step()
    assert backward.status == "stepped"
    assert backward.raw_steps == source_step_one - source_step_zero
    assert runner.current.steps == source_step_zero
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "START_STEP"


def test_raw_trace_grouped_source_step_back_rewinds_to_initial_boundary() -> None:
    tape = load_fixture("incrementer").build_encoded_tape()
    program = build_universal_meta_asm(tape.encoding)
    alphabet = sorted(set(tape.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        tape.runtime_tape,
        head=start_head_from_encoded_tape(tape),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    runner.step()
    expected_snapshot = runner.current
    backward = runner.back_to_previous_source_step()

    assert backward.status == "at_start"
    assert backward.raw_steps == 0
    assert runner.current == expected_snapshot
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "START_STEP"


def test_raw_trace_raw_and_group_steps_after_halt_or_stuck() -> None:
    builder = TMBuilder(["0"])
    builder.emit("start", "0", builder.halt_state, "0", S)
    halted_runner = RawTraceRunner(builder.build("start"), {0: "0"}, head=0)

    first_step = halted_runner.step()
    assert first_step.status == "stepped"
    assert halted_runner.is_halted is True
    halted_instruction = halted_runner.step_to_next_instruction()
    halted_source = halted_runner.step_to_next_source_step()
    halted_routine = halted_runner.step_to_next_routine()
    assert halted_instruction.status == "halted"
    assert halted_instruction.raw_steps == 0
    assert halted_source.status == "halted"
    assert halted_source.raw_steps == 0
    assert halted_routine.status == "halted"
    assert halted_routine.raw_steps == 0

    stuck_builder = TMBuilder(["0"])
    stuck_runner = RawTraceRunner(stuck_builder.build("start"), {0: "1"}, head=0)

    stuck_step = stuck_runner.step()
    assert stuck_step.status == "stuck"
    stuck_instruction = stuck_runner.step_to_next_instruction()
    stuck_source = stuck_runner.step_to_next_source_step()
    assert stuck_instruction.status == "stuck"
    assert stuck_instruction.raw_steps == 0
    assert stuck_source.status == "stuck"
    assert stuck_source.raw_steps == 0


def test_raw_trace_grouped_step_without_source_map_returns_unmapped() -> None:
    builder = TMBuilder(["0"])
    builder.emit("start", "0", "middle", "0", R)
    builder.emit("middle", "0", "done", "0", R)
    builder.emit("done", "0", "done", "0", S)
    runner = RawTraceRunner(builder.build("start"), {0: "0"}, head=0)

    grouped = runner.step_to_next_instruction()
    assert grouped.status == "unmapped"
    assert grouped.raw_steps == 0
    assert grouped.snapshot == runner.current

    step = runner.step()
    assert step.status == "stepped"
    assert runner.current.state == "middle"


def test_raw_trace_grouped_forward_obeys_max_raw() -> None:
    program = Program(blocks=(Block("ENTRY", (Seek(RULES, "R"), Goto("DONE"))),), entry_label="ENTRY")
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(
        lowered.raw_program,
        {0: "0", 1: "0", 2: RULES},
        head=0,
        state="ENTRY",
        source_map=lowered.source_map,
    )

    forward = runner.step_to_next_instruction(max_raw=1)

    assert forward.status == "max_raw"
    assert forward.raw_steps == 1
    assert runner.current.steps == 1


def test_raw_trace_truncates_history_when_stepping_after_rewind() -> None:
    builder = TMBuilder(["0"], blank="0")
    builder.emit("start", "0", "middle", "0", R)
    builder.emit("middle", "0", "second", "0", R)
    builder.emit("second", "0", "last", "0", R)
    builder.emit("last", "0", builder.halt_state, "0", S)
    runner = RawTraceRunner(builder.build("start"), {0: "0"}, head=0)

    runner.step()
    runner.step()
    runner.step()
    assert runner.current.steps == 3
    assert runner.history_cursor == 3
    assert runner.latest_history_index == 3

    runner.back()
    runner.step()
    assert runner.current.steps == 3
    assert runner.history_cursor == 3
    assert runner.latest_history_index == 3


def test_raw_trace_grouped_source_step_uses_configured_boundary_label() -> None:
    program = Program(
        blocks=(
            Block("CYCLE", (Seek(RULES, "R"), Goto("OTHER"))),
            Block("OTHER", (Goto("CYCLE"),)),
        ),
        entry_label="CYCLE",
    )
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(
        lowered.raw_program,
        {0: "0", 1: RULES},
        head=0,
        state="CYCLE",
        source_map=lowered.source_map,
        source_step_block_label="CYCLE",
    )

    forward = runner.step_to_next_source_step()

    assert forward.status == "stepped"
    assert runner.current_transition_source is not None
    assert runner.current_transition_source.block_label == "CYCLE"


def test_raw_trace_current_view_projects_raw_and_decoded_state() -> None:
    tape = load_fixture("incrementer").build_encoded_tape()
    program = build_universal_meta_asm(tape.encoding)
    alphabet = sorted(set(tape.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        tape.runtime_tape,
        head=start_head_from_encoded_tape(tape),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    view = runner.current_view(encoding=tape.encoding)

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
    tape = load_fixture("incrementer").build_encoded_tape()
    start_head = start_head_from_encoded_tape(tape)
    builder = TMBuilder(sorted(set(tape.linear()) | {"0", "1"}), blank=tape.encoding.blank)
    builder.emit("start", CUR_STATE, builder.halt_state, "0", S)
    runner = RawTraceRunner(builder.build("start"), tape.runtime_tape, head=start_head)

    stepped = runner.step()
    view = runner.current_view(encoding=tape.encoding)

    assert stepped.status == "stepped"
    assert view.decoded_view is None
    assert view.decode_error is not None
    assert "CUR_STATE" in view.decode_error


def test_format_trace_view_renders_raw_snapshot_transitions_and_status() -> None:
    builder = TMBuilder(["0", "1"])
    builder.emit("start", "0", "scan", "1", R)
    builder.emit("scan", "1", builder.halt_state, "1", S)
    runner = RawTraceRunner(builder.build("start"), {0: "0", 1: "1"}, head=0)

    initial = format_trace_view(runner.current_view(), raw_window=1)
    runner.step()
    stepped = format_trace_view(runner.current_view(), raw_window=1)

    assert initial == "\n".join([
        "snapshot: step=0 state='start' head=0",
        "raw tape: -1:'.' [0:'0'] 1:'1'",
        "next raw: ('start', '0') -> ('scan', '1', R)",
        "source: <unmapped>",
        "last raw: <none>",
        "semantic: <not requested>",
    ])
    assert stepped == "\n".join([
        "snapshot: step=1 state='scan' head=1",
        "raw tape: 0:'1' [1:'1'] 2:'.'",
        "next raw: ('scan', '1') -> ('U_HALT', '1', S)",
        "source: <unmapped>",
        "last raw: ('start', '0') -> ('scan', '1', R)",
        "semantic: <not requested>",
    ])


def test_format_source_location_and_group_step_result_render_lowered_location() -> None:
    program = Program(blocks=(Block("ENTRY", (Seek(RULES, "L"), Goto("DONE"))),), entry_label="ENTRY")
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(
        lowered.raw_program,
        {0: RULES},
        head=0,
        state="ENTRY",
        source_map=lowered.source_map,
    )

    source = runner.current_transition_source
    result = runner.step_to_next_instruction()

    assert source is not None
    assert format_source_location(source) == "\n".join([
        "source: block=ENTRY instruction=0 routine=0:seek op=0",
        "row: state='ENTRY' read='#RULES'",
        "instruction: SEEK #RULES L",
    ])
    assert format_group_step_result(result, source=runner.current_transition_source) == "\n".join([
        "group step: status=stepped raw_steps=1",
        f"snapshot: step={result.snapshot.steps} state={result.snapshot.state!r} head={result.snapshot.head}",
        "source: block=ENTRY instruction=1 routine=1:goto op=0",
        f"row: state={runner.current_transition_source.state!r} read={runner.current_transition_source.read_symbol!r}",
        "instruction: GOTO DONE",
    ])


def test_format_trace_view_renders_semantic_summary_for_decoded_utm_view() -> None:
    tape = load_fixture("incrementer").build_encoded_tape()
    program = build_universal_meta_asm(tape.encoding)
    alphabet = sorted(set(tape.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        tape.runtime_tape,
        head=start_head_from_encoded_tape(tape),
        state=program.entry_label,
        source_map=lowered.source_map,
    )

    rendered = format_trace_view(runner.current_view(encoding=tape.encoding), raw_window=1, semantic_window=2)

    assert rendered == "\n".join([
        "snapshot: step=0 state='START_STEP' head=-169",
        "raw tape: -170:'#REGS' [-169:'#CUR_STATE'] -168:'1'",
        "next raw: ('START_STEP', '#CUR_STATE') -> ('START_STEP', '#CUR_STATE', L)",
        "source: block=START_STEP instruction=0 routine=0:compare_global_global op=0",
        "row: state='START_STEP' read='#CUR_STATE'",
        "instruction: COMPARE_GLOBAL_GLOBAL #CUR_STATE #HALT_STATE 2",
        "last raw: <none>",
        "semantic: state='qFindMargin' head=0",
        "semantic tape: -2:'_' -1:'_' [0:'1'] 1:'0' 2:'1'",
        "registers: cur='qFindMargin' read='_' write='_' next='qFindMargin' move=L cmp='0' tmp='00'",
    ])
