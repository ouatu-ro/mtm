from mtm import (
    build_universal_meta_asm,
    load_fixture,
    lower_instruction,
    lower_instruction_sequence,
    lower_program_to_raw_tm,
    run_meta_asm_block,
    run_meta_asm_host,
    run_raw_tm,
)
from mtm.lowering import ACTIVE_RULE
from mtm.meta_asm import CopyGlobalToHeadSymbol, CopyHeadSymbolTo
from mtm.lowering_checks import lowering_smoke_rows
from mtm.outer_tape import CMP_FLAG, CUR_STATE, CUR_SYMBOL, HEAD, NO_HEAD, materialize_raw_tape, split_outer_tape
from mtm.raw_tm import TMBuilder


def _set_global_bits(band, marker: str, bits: str):
    left_band = list(band.left_band)
    start = left_band.index(marker) + 1
    left_band[start:start + len(bits)] = list(bits)
    return materialize_raw_tape(left_band, band.right_band)


def _set_head_cell(band, cell_index: int):
    span = 3 + band.encoding.symbol_width
    right_band = list(band.right_band)
    for index, token in enumerate(right_band):
        if token in {HEAD, NO_HEAD}:
            right_band[index] = NO_HEAD
    right_band[1 + cell_index * span + 1] = HEAD
    return materialize_raw_tape(band.left_band, right_band)


def _set_global_bits_on_tape(band, outer_tape, marker: str, bits: str):
    left_band, right_band = split_outer_tape(outer_tape)
    start = left_band.index(marker) + 1
    left_band[start:start + len(bits)] = list(bits)
    return materialize_raw_tape(left_band, right_band)


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
    assert got["COPY_LOCAL_GLOBAL"][3] == "#WRITE_SYMBOL=00"
    assert got["COPY_GLOBAL_GLOBAL"][:2] == ["stuck", "DONE"]
    assert got["COPY_GLOBAL_GLOBAL"][3] == "#CUR_SYMBOL=01"
    assert got["COPY_HEAD_SYMBOL_TO"][:2] == ["stuck", "DONE"]
    assert got["COPY_HEAD_SYMBOL_TO"][3] == "#CUR_SYMBOL=01"
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
        host = run_meta_asm_block(program, band.encoding, prepared_tape, label="START_STEP", max_steps=10)
        builder = TMBuilder(alphabet)
        lower_instruction_sequence(builder, start_block.instructions, start_state="START_STEP", exit_label="DONE")
        result = run_raw_tm(builder.build("START_STEP"), prepared_tape, head=cur_state_head, max_steps=200)
        final_left_band, _ = split_outer_tape(result["tape"])
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
    lower_instruction(builder, CopyHeadSymbolTo(CUR_SYMBOL, band.encoding.symbol_width), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), prepared_tape, head=1 + 4 * (3 + band.encoding.symbol_width), max_steps=1000)
    final_left_band, _ = split_outer_tape(result["tape"])
    cur_symbol_index = final_left_band.index(CUR_SYMBOL)

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert "".join(final_left_band[cur_symbol_index + 1:cur_symbol_index + 3]) == "10"


def test_copy_global_to_head_symbol_matches_later_cell() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    builder = TMBuilder(alphabet)
    prepared_tape = _set_global_bits_on_tape(band, _set_head_cell(band, 3), CUR_SYMBOL, "00")
    lower_instruction(builder, CopyGlobalToHeadSymbol(CUR_SYMBOL, band.encoding.symbol_width), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), prepared_tape, head=1 + 3 * (3 + band.encoding.symbol_width), max_steps=1500)
    _, final_right_band = split_outer_tape(result["tape"])

    assert result["status"] == "stuck"
    assert result["state"] == "DONE"
    assert "".join(final_right_band[18:20]) == "00"


def test_lowered_incrementer_matches_host_run() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    left_addresses = list(range(-len(band.left_band), 0))
    start_head = left_addresses[band.left_band.index(CUR_STATE)]

    host_status, host_outer_tape, _host_trace, _host_reason = run_meta_asm_host(program, band.encoding, band.outer_tape, max_steps=500)
    raw_tm = lower_program_to_raw_tm(program, alphabet)
    raw = run_raw_tm(raw_tm, band.outer_tape, head=start_head, max_steps=200_000)
    raw_left_band, raw_right_band = split_outer_tape(raw["tape"])
    host_left_band, host_right_band = split_outer_tape(host_outer_tape)

    assert host_status == "halted"
    assert raw["status"] == "halted"
    assert raw["state"] == "U_HALT"
    assert raw_left_band == host_left_band
    assert raw_right_band == host_right_band
