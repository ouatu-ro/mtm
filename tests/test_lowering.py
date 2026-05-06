from mtm import TMBand, load_fixture
from mtm.lowering import ACTIVE_RULE, CFGTransition, HeadAt, KeepWrite, NameSupply, ReadAny, ReadAnyExcept, ReadSymbol, ReadSymbols, RoutineCFG, Routine, SeekOp, WriteSymbolAction, assemble_cfg, compile_routine, instruction_sequence_to_routines, lower_instruction_to_routine, lower_program_to_raw_tm, lower_program_with_source_map, program_to_cfgs, validate_cfg, validate_program_cfgs
from mtm.meta_asm import Block, BranchCmp, CopyGlobalToHeadSymbol, CopyHeadSymbolTo, FindHeadCell, Goto, MoveSimHeadLeft, MoveSimHeadRight, Program, Seek, format_instruction
from mtm.meta_asm import build_universal_meta_asm
from mtm.meta_asm_host import run_meta_asm_block_runtime, run_meta_asm_runtime
from tests.lowering_checks import assemble_instruction, lowering_smoke_rows
from mtm.semantic_objects import decoded_view_from_encoded_band
from mtm.source_encoding import encode_symbol
from mtm.utm_band_layout import CELL, CMP_FLAG, CUR_STATE, CUR_SYMBOL, HEAD, NO_HEAD, RULES, TAPE_LEFT, compile_tm_to_universal_tape, materialize_runtime_tape, split_runtime_tape
from mtm.raw_transition_tm import TMBuilder, run_raw_tm


def _set_global_bits(band, marker: str, bits: str):
    left_band = list(band.left_band)
    start = left_band.index(marker) + 1
    left_band[start:start + len(bits)] = list(bits)
    return materialize_runtime_tape(left_band, band.right_band)


def _set_head_cell(band, cell_index: int):
    span = 3 + band.encoding.symbol_width
    right_band = list(band.right_band)
    for index, token in enumerate(right_band):
        if token in {HEAD, NO_HEAD}:
            right_band[index] = NO_HEAD
    right_band[1 + cell_index * span + 1] = HEAD
    return materialize_runtime_tape(band.left_band, right_band)


def _runtime_tape_with_no_head(band):
    right_band = [NO_HEAD if token == HEAD else token for token in band.right_band]
    return materialize_runtime_tape(band.left_band, right_band)


def _cell_address(band, cell_index: int) -> int:
    return [index for index, token in enumerate(band.right_band) if token == CELL][cell_index]


def _left_cell_address(band, cell_index: int) -> int:
    left_addresses = list(range(-len(band.left_band), 0))
    cells = [
        left_addresses[index]
        for index, token in enumerate(band.left_band[:band.left_band.index(TAPE_LEFT)])
        if token == CELL
    ]
    return cells[cell_index]


def _set_global_bits_on_runtime_tape(band, runtime_tape, marker: str, bits: str):
    left_band, right_band = split_runtime_tape(runtime_tape)
    start = left_band.index(marker) + 1
    left_band[start:start + len(bits)] = list(bits)
    return materialize_runtime_tape(left_band, right_band)


def _assemble_sequence(builder: TMBuilder, instructions, *, start_state: str, exit_label: str) -> None:
    for index, routine in enumerate(
        instruction_sequence_to_routines(
            instructions,
            start_state=start_state,
            exit_label=exit_label,
            names=NameSupply("test_sequence"),
        )
    ):
        cfg = compile_routine(routine, NameSupply(f"test_sequence_{index}"), halt_state=builder.halt_state)
        validate_cfg(cfg, builder.alphabet)
        assemble_cfg(builder, cfg)


def test_first_lowered_fragments_smoke() -> None:
    rows = lowering_smoke_rows(load_fixture("incrementer"))
    got = {row[0]: row[1:] for row in rows}

    assert got["HALT"][:2] == ["halted", "U_HALT"]
    assert got["GOTO"][:2] == ["stuck", "TARGET"]
    assert got["BRANCH_CMP"][:2] == ["stuck", "NEQ"]
    assert got["BRANCH_AT"][:2] == ["stuck", "YES"]
    assert got["WRITE_GLOBAL"][:2] == ["stuck", "DONE"]
    assert got["WRITE_GLOBAL"][3] == "#CUR_SYMBOL=01"
    assert got["SEEK"][:2] == ["stuck", "DONE"]
    assert got["SEEK"][2] == -128
    assert got["SEEK_ONE_OF"][:2] == ["stuck", "DONE"]
    assert got["SEEK_ONE_OF"][2] == -127
    assert got["FIND_FIRST_RULE"][:2] == ["stuck", "DONE"]
    assert got["FIND_FIRST_RULE"][2] == -127
    assert got["FIND_NEXT_RULE"][:2] == ["stuck", "DONE"]
    assert got["FIND_NEXT_RULE"][2] == -106
    assert got["FIND_HEAD_CELL"][:2] == ["stuck", "DONE"]
    assert got["FIND_HEAD_CELL"][2] == 1
    assert got["MOVE_SIM_HEAD_RIGHT"][:2] == ["stuck", "DONE"]
    assert got["MOVE_SIM_HEAD_RIGHT"][2] == 6
    assert got["MOVE_SIM_HEAD_LEFT"][:2] == ["stuck", "DONE"]
    assert got["MOVE_SIM_HEAD_LEFT"][2] == 1
    assert got["COPY_LOCAL_GLOBAL"][:2] == ["stuck", "DONE"]
    assert got["COPY_LOCAL_GLOBAL"][3] == "#WRITE_SYMBOL=01"
    assert got["COPY_GLOBAL_GLOBAL"][:2] == ["stuck", "DONE"]
    assert got["COPY_GLOBAL_GLOBAL"][3] == "#CUR_SYMBOL=01"
    assert got["COPY_HEAD_SYMBOL_TO"][:2] == ["stuck", "DONE"]
    assert got["COPY_HEAD_SYMBOL_TO"][3] == "#CUR_SYMBOL=10"
    assert got["COPY_GLOBAL_TO_HEAD_SYMBOL"][:2] == ["stuck", "DONE"]
    assert got["COPY_GLOBAL_TO_HEAD_SYMBOL"][3] == "head_symbol=00"
    assert got["COMPARE_GLOBAL_LITERAL"][:2] == ["stuck", "DONE"]
    assert got["COMPARE_GLOBAL_LITERAL"][3] == "#CMP_FLAG=1"
    assert got["COMPARE_GLOBAL_LOCAL"][:2] == ["stuck", "DONE"]
    assert got["COMPARE_GLOBAL_LOCAL"][3] == "#CMP_FLAG=1"


def test_lowered_start_step_matches_host_block() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    program = build_universal_meta_asm(band.encoding)
    start_block = next(block for block in program.blocks if block.label == "START_STEP")
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    left_addresses = list(range(-len(band.left_band), 0))
    cur_state_head = left_addresses[band.left_band.index(CUR_STATE)]

    for cur_state_bits, expected_label, expected_cmp in [
        ("10", "FIND_HEAD", "0"),
        ("01", "HALT", "1"),
    ]:
        prepared_tape = _set_global_bits(band, CUR_STATE, cur_state_bits)
        host = run_meta_asm_block_runtime(program, band.encoding, prepared_tape, label="START_STEP", max_steps=10)
        builder = TMBuilder(alphabet)
        _assemble_sequence(builder, start_block.instructions, start_state="START_STEP", exit_label="DONE")
        result = run_raw_tm(builder.build("START_STEP"), prepared_tape, head=cur_state_head, max_steps=200)
        final_left_band, _ = split_runtime_tape(result["tape"])
        cmp_index = final_left_band.index(CMP_FLAG)

        assert host["label"] == expected_label
        assert result["state"] == expected_label
        assert final_left_band[cmp_index + 1] == expected_cmp


def test_copy_head_symbol_to_matches_later_blank_cell() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    prepared_tape = _set_head_cell(band, 4)
    assemble_instruction(builder, CopyHeadSymbolTo(CUR_SYMBOL, band.encoding.symbol_width), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), prepared_tape, head=1 + 4 * (3 + band.encoding.symbol_width), max_steps=1000)
    final_left_band, _ = split_runtime_tape(result["tape"])
    cur_symbol_index = final_left_band.index(CUR_SYMBOL)

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert "".join(final_left_band[cur_symbol_index + 1:cur_symbol_index + 3]) == "00"


def test_copy_head_symbol_to_matches_left_band_cell() -> None:
    fixture = load_fixture("incrementer")
    source_band = TMBand.from_bands(right_band=("0",), left_band=("1",), head=-1, blank="_")
    band = compile_tm_to_universal_tape(
        fixture.tm_program,
        source_band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    assemble_instruction(builder, CopyHeadSymbolTo(CUR_SYMBOL, band.encoding.symbol_width), state="start", continuation_label="DONE")

    result = run_raw_tm(builder.build("start"), band.runtime_tape, head=_left_cell_address(band, 0), max_steps=2000)
    final_left_band, _ = split_runtime_tape(result["tape"])
    cur_symbol_index = final_left_band.index(CUR_SYMBOL)

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert tuple(final_left_band[cur_symbol_index + 1:cur_symbol_index + 1 + band.encoding.symbol_width]) == encode_symbol(band.encoding, "1")


def test_copy_global_to_head_symbol_matches_later_cell() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    prepared_tape = _set_global_bits_on_runtime_tape(band, _set_head_cell(band, 3), CUR_SYMBOL, "00")
    assemble_instruction(builder, CopyGlobalToHeadSymbol(CUR_SYMBOL, band.encoding.symbol_width), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), prepared_tape, head=1 + 3 * (3 + band.encoding.symbol_width), max_steps=1500)
    _, final_right_band = split_runtime_tape(result["tape"])

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert "".join(final_right_band[18:20]) == "00"


def test_copy_global_to_head_symbol_matches_left_band_cell() -> None:
    fixture = load_fixture("incrementer")
    source_band = TMBand.from_bands(right_band=("0",), left_band=("1",), head=-1, blank="_")
    band = compile_tm_to_universal_tape(
        fixture.tm_program,
        source_band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    prepared_tape = _set_global_bits_on_runtime_tape(band, band.runtime_tape, CUR_SYMBOL, "".join(encode_symbol(band.encoding, "0")))
    assemble_instruction(builder, CopyGlobalToHeadSymbol(CUR_SYMBOL, band.encoding.symbol_width), state="start", continuation_label="DONE")

    result = run_raw_tm(builder.build("start"), prepared_tape, head=_left_cell_address(band, 0), max_steps=3000)
    final_left_band, _ = split_runtime_tape(result["tape"])
    head_flag_index = final_left_band.index(HEAD)

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert tuple(final_left_band[head_flag_index + 1:head_flag_index + 1 + band.encoding.symbol_width]) == encode_symbol(band.encoding, "0")


def test_find_head_cell_branches_to_stuck_at_end_tape_boundary() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    assemble_instruction(builder, FindHeadCell(), state="start", continuation_label="DONE")

    result = run_raw_tm(builder.build("start"), _runtime_tape_with_no_head(band), head=0, max_steps=500)

    assert result["status"] == "stuck"
    assert result["state"] == "STUCK"


def test_move_sim_head_right_constructs_blank_at_end_tape_boundary() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    last_cell = len([token for token in band.right_band if token == CELL]) - 1
    prepared_tape = _set_head_cell(band, last_cell)
    assemble_instruction(builder, MoveSimHeadRight(band.encoding.symbol_width), state="start", continuation_label="DONE")

    result = run_raw_tm(builder.build("start"), prepared_tape, head=_cell_address(band, last_cell), max_steps=500)

    _, final_right_band = split_runtime_tape(result["tape"])

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert final_right_band[result["head"]] == CELL
    assert final_right_band[result["head"] + 1] == HEAD
    symbol_end = result["head"] + 2 + band.encoding.symbol_width
    assert tuple(final_right_band[result["head"] + 2:symbol_end]) == encode_symbol(band.encoding, band.encoding.blank)


def test_move_sim_head_left_constructs_blank_at_tape_left_boundary() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    assemble_instruction(builder, MoveSimHeadLeft(band.encoding.symbol_width), state="start", continuation_label="DONE")

    result = run_raw_tm(builder.build("start"), band.runtime_tape, head=_cell_address(band, 0), max_steps=500)

    final_left_band, _ = split_runtime_tape(result["tape"])
    left_cell_index = final_left_band.index(CELL)

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert final_left_band[left_cell_index + 1] == HEAD
    symbol_end = left_cell_index + 2 + band.encoding.symbol_width
    assert tuple(final_left_band[left_cell_index + 2:symbol_end]) == encode_symbol(band.encoding, band.encoding.blank)


def test_move_sim_head_left_crosses_to_materialized_left_band() -> None:
    fixture = load_fixture("incrementer")
    source_band = TMBand.from_bands(right_band=("1",), left_band=("_",), head=0, blank="_")
    band = compile_tm_to_universal_tape(
        fixture.tm_program,
        source_band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    assemble_instruction(builder, MoveSimHeadLeft(band.encoding.symbol_width), state="start", continuation_label="DONE")

    result = run_raw_tm(builder.build("start"), band.runtime_tape, head=_cell_address(band, 0), max_steps=2000)
    final_left_band, _ = split_runtime_tape(result["tape"])
    left_cell_index = final_left_band.index(CELL)

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert result["head"] == _left_cell_address(band, 0)
    assert final_left_band[left_cell_index + 1] == HEAD


def test_meta_asm_host_finds_and_reads_left_band_head_cell() -> None:
    fixture = load_fixture("incrementer")
    source_band = TMBand.from_bands(right_band=("0",), left_band=("1",), head=-1, blank="_")
    band = compile_tm_to_universal_tape(
        fixture.tm_program,
        source_band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    program = Program(
        blocks=(Block("ENTRY", (FindHeadCell(), CopyHeadSymbolTo(CUR_SYMBOL, band.encoding.symbol_width))),),
        entry_label="ENTRY",
    )

    status, runtime_tape, trace, _reason = run_meta_asm_runtime(program, band.encoding, band.runtime_tape, max_steps=10)
    final_left_band, _ = split_runtime_tape(runtime_tape)
    cur_symbol_index = final_left_band.index(CUR_SYMBOL)

    assert status == "halted"
    assert trace[0]["head"] == _left_cell_address(band, 0)
    assert tuple(final_left_band[cur_symbol_index + 1:cur_symbol_index + 1 + band.encoding.symbol_width]) == encode_symbol(band.encoding, "1")


def test_meta_asm_host_moves_between_right_and_left_simulated_tape() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    program = Program(
        blocks=(
            Block(
                "ENTRY",
                (
                    FindHeadCell(),
                    MoveSimHeadLeft(band.encoding.symbol_width),
                    MoveSimHeadRight(band.encoding.symbol_width),
                ),
            ),
        ),
        entry_label="ENTRY",
    )

    status, runtime_tape, trace, _reason = run_meta_asm_runtime(program, band.encoding, band.runtime_tape, max_steps=10)
    view = decoded_view_from_encoded_band(type(band).from_runtime_tape(band.encoding, runtime_tape))

    assert status == "halted"
    assert trace[1]["head"] < 0
    assert trace[2]["head"] == 1
    assert view.simulated_tape.left_band == ("_",)
    assert view.simulated_tape.head == 0


def test_lower_instruction_to_routine_is_inspectable() -> None:
    routine = lower_instruction_to_routine(Seek(RULES, "L"), state="start", cont="DONE")

    assert routine.name == "seek"
    assert routine.entry == "start"
    assert routine.exits == ("DONE",)
    assert routine.falls_through
    assert routine.requires.__class__.__name__ == "HeadOnRuntimeTape"
    assert routine.ensures == HeadAt(RULES)
    assert routine.ops == (SeekOp("start", "DONE", frozenset({RULES}), "L"),)


def test_compile_routine_keeps_seek_cfg_structured() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    routine = lower_instruction_to_routine(Seek(RULES, "L"), state="start", cont="DONE")
    cfg = compile_routine(routine, NameSupply("seek_test"))
    builder = TMBuilder(alphabet)

    validate_cfg(cfg, alphabet)
    assemble_cfg(builder, cfg)
    result = run_raw_tm(builder.build("start"), band.runtime_tape, head=0, max_steps=300)

    assert cfg.entry == "start"
    assert cfg.exits == ("DONE",)
    assert len(cfg.transitions) == 2
    assert isinstance(cfg.transitions[0].reads, ReadSymbols)
    assert isinstance(cfg.transitions[1].reads, ReadAnyExcept)
    assert not any(isinstance(transition.reads, ReadAny) for transition in cfg.transitions)
    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert result["head"] == -128


def test_validate_cfg_rejects_duplicate_read_coverage() -> None:
    cfg = RoutineCFG(
        entry="start",
        exits=("done",),
        internal_states=("start",),
        transitions=(
            CFGTransition("start", ReadAny(), "done", KeepWrite(), 0),
            CFGTransition("start", ReadSymbol("0"), "done", KeepWrite(), 0),
        ),
    )

    try:
        validate_cfg(cfg, ("0", "1"))
    except ValueError as exc:
        assert "duplicate CFG transition" in str(exc)
    else:
        raise AssertionError("expected duplicate CFG coverage to be rejected")


def test_validate_cfg_rejects_empty_read_sets() -> None:
    cfg = RoutineCFG(
        entry="start",
        exits=("done",),
        internal_states=("start",),
        transitions=(
            CFGTransition("start", ReadSymbols(frozenset({"missing"})), "done", KeepWrite(), 0),
        ),
    )

    try:
        validate_cfg(cfg, ("0", "1"))
    except ValueError as exc:
        assert "outside alphabet" in str(exc)
    else:
        raise AssertionError("expected missing CFG read symbol to be rejected")


def test_validate_cfg_rejects_writes_outside_alphabet() -> None:
    cfg = RoutineCFG(
        entry="start",
        exits=("done",),
        internal_states=("start",),
        transitions=(
            CFGTransition("start", ReadSymbol("0"), "done", WriteSymbolAction("missing"), 0),
        ),
    )

    try:
        validate_cfg(cfg, ("0", "1"))
    except ValueError as exc:
        assert "writes symbols outside alphabet" in str(exc)
    else:
        raise AssertionError("expected missing CFG write symbol to be rejected")


def test_terminal_routines_expose_real_exits() -> None:
    goto = lower_instruction_to_routine(Goto("TARGET"), state="start", cont="NEXT")
    branch = lower_instruction_to_routine(BranchCmp("EQ", "NEQ"), state="start", cont="NEXT")

    assert goto.exits == ("TARGET",)
    assert not goto.falls_through
    assert branch.exits == ("EQ", "NEQ")
    assert not branch.falls_through


def test_instruction_sequence_rejects_terminal_instruction_before_end() -> None:
    try:
        instruction_sequence_to_routines(
            (Goto("TARGET"), Seek(RULES, "L")),
            start_state="start",
            exit_label="DONE",
            names=NameSupply("bad_sequence"),
        )
    except ValueError as exc:
        assert "terminal instruction before end of block" in str(exc)
    else:
        raise AssertionError("expected terminal instruction placement to be rejected")


def test_name_supply_named_does_not_consume_ids_for_existing_labels() -> None:
    names = NameSupply("name")

    first = names.named("@loop")
    second = names.named("@loop")
    fresh = names.fresh("loop")

    assert first == second
    assert fresh == "name_loop_1"


def test_compile_routine_rejects_bad_direction() -> None:
    routine = Routine(
        name="bad_seek",
        entry="start",
        exits=("done",),
        falls_through=True,
        ops=(SeekOp("start", "done", frozenset({"0"}), "sideways"),),
    )

    try:
        compile_routine(routine, NameSupply("bad_direction"))
    except ValueError as exc:
        assert "unsupported direction" in str(exc)
    else:
        raise AssertionError("expected bad direction to be rejected")


def test_validate_cfg_rejects_bad_move() -> None:
    cfg = RoutineCFG(
        entry="start",
        exits=("done",),
        internal_states=("start",),
        transitions=(
            CFGTransition("start", ReadSymbol("0"), "done", KeepWrite(), 99),
        ),
    )

    try:
        validate_cfg(cfg, ("0",))
    except ValueError as exc:
        assert "invalid move" in str(exc)
    else:
        raise AssertionError("expected invalid move to be rejected")


def test_validate_cfg_rejects_exit_sources() -> None:
    cfg = RoutineCFG(
        entry="start",
        exits=("done",),
        internal_states=("start",),
        transitions=(
            CFGTransition("start", ReadSymbol("0"), "done", KeepWrite(), 0),
            CFGTransition("done", ReadSymbol("1"), "start", KeepWrite(), 0),
        ),
    )

    try:
        validate_cfg(cfg, ("0", "1"))
    except ValueError as exc:
        assert "exit states have outgoing transitions" in str(exc)
    else:
        raise AssertionError("expected exit source transition to be rejected")


def test_validate_cfg_rejects_internal_exit_overlap() -> None:
    cfg = RoutineCFG(
        entry="start",
        exits=("done",),
        internal_states=("start", "done"),
        transitions=(
            CFGTransition("start", ReadSymbol("0"), "done", KeepWrite(), 0),
        ),
    )

    try:
        validate_cfg(cfg, ("0",))
    except ValueError as exc:
        assert "both internal and exits" in str(exc)
    else:
        raise AssertionError("expected internal/exit overlap to be rejected")


def test_validate_program_cfgs_rejects_cross_routine_duplicate_coverage() -> None:
    cfgs = (
        RoutineCFG(
            entry="start",
            exits=("done_a",),
            internal_states=("start",),
            transitions=(CFGTransition("start", ReadSymbol("0"), "done_a", KeepWrite(), 0),),
        ),
        RoutineCFG(
            entry="start",
            exits=("done_b",),
            internal_states=("start",),
            transitions=(CFGTransition("start", ReadSymbol("0"), "done_b", KeepWrite(), 0),),
        ),
    )

    try:
        validate_program_cfgs(cfgs, ("0",))
    except ValueError as exc:
        assert "duplicate program CFG transition" in str(exc)
    else:
        raise AssertionError("expected cross-routine duplicate transition to be rejected")


def test_program_to_cfgs_returns_inspectable_cfgs_before_assembly() -> None:
    fixture = load_fixture("incrementer")
    program = build_universal_meta_asm(fixture.build_band().encoding)
    cfgs = program_to_cfgs(program)

    assert cfgs
    assert all(cfg.transitions for cfg in cfgs)


def test_block_lowering_uses_block_level_continuation_names() -> None:
    program = Program(
        blocks=(Block("START_STEP", (Seek(RULES, "L"), Goto("DONE"))),),
        entry_label="START_STEP",
    )

    cfgs = program_to_cfgs(program)

    assert cfgs[0].transitions[0].target == "program_START_STEP_cont_0_0"
    assert cfgs[1].entry == "program_START_STEP_cont_0_0"
    assert cfgs[1].transitions[0].target == "DONE"


def test_lower_program_with_source_map_maps_seek_rows_back_to_instruction_and_op() -> None:
    instruction = Seek(RULES, "L")
    program = Program(blocks=(Block("ENTRY", (instruction,)),), entry_label="ENTRY")

    lowered = lower_program_with_source_map(program, ("0", RULES))
    cfg = lowered.cfgs[0]

    on_marker = lowered.source_map.lookup(cfg.entry, RULES)
    on_other = lowered.source_map.lookup(cfg.entry, "0")

    assert on_marker is not None
    assert on_other is not None
    assert on_marker.block_label == "ENTRY"
    assert on_marker.instruction_index == 0
    assert on_marker.instruction == instruction
    assert on_marker.instruction_text == format_instruction(instruction)
    assert on_marker.routine_index == 0
    assert on_marker.routine_name == "seek"
    assert on_marker.op_index == 0
    assert on_marker.op == SeekOp("ENTRY", "program_ENTRY_exit_0", frozenset({RULES}), "L")
    assert on_other.block_label == on_marker.block_label
    assert on_other.instruction_index == on_marker.instruction_index
    assert on_other.routine_index == on_marker.routine_index
    assert on_other.op_index == on_marker.op_index


def test_lower_program_with_source_map_maps_second_routine_rows_back_to_goto() -> None:
    instructions = (Seek(RULES, "L"), Goto("DONE"))
    program = Program(blocks=(Block("ENTRY", instructions),), entry_label="ENTRY")

    lowered = lower_program_with_source_map(program, ("0", RULES))
    goto_cfg = lowered.cfgs[1]
    source = lowered.source_map.lookup(goto_cfg.entry, "0")

    assert source is not None
    assert source.block_label == "ENTRY"
    assert source.instruction_index == 1
    assert source.instruction == instructions[1]
    assert source.instruction_text == format_instruction(instructions[1])
    assert source.routine_index == 1
    assert source.routine_name == "goto"
    assert source.op_index == 0


def test_lowered_incrementer_matches_host_run() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    left_addresses = list(range(-len(band.left_band), 0))
    start_head = left_addresses[band.left_band.index(CUR_STATE)]

    host_status, host_runtime_tape, _host_trace, _host_reason = run_meta_asm_runtime(program, band.encoding, band.runtime_tape, max_steps=500)
    raw_tm = lower_program_to_raw_tm(program, alphabet)
    raw = run_raw_tm(raw_tm, band.runtime_tape, head=start_head, max_steps=200_000)
    raw_left_band, raw_right_band = split_runtime_tape(raw["tape"])
    host_left_band, host_right_band = split_runtime_tape(host_runtime_tape)

    assert host_status == "halted"
    assert raw["status"] == "halted"
    assert raw["state"] == "U_HALT"
    assert raw_left_band == host_left_band
    assert raw_right_band == host_right_band
