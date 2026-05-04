from mtm import build_universal_meta_asm, load_fixture, lower_instruction_sequence, run_meta_asm_block, run_raw_tm
from mtm.lowering_checks import lowering_smoke_rows
from mtm.outer_tape import CMP_FLAG, CUR_STATE, place_on_negative_side, place_on_positive_side, split_outer_tape
from mtm.raw_tm import TMBuilder


def _set_global_bits(band, marker: str, bits: str):
    left_band = list(band.left_band)
    start = left_band.index(marker) + 1
    left_band[start:start + len(bits)] = list(bits)
    outer_tape = {}
    outer_tape.update(place_on_negative_side(left_band, start=-1))
    outer_tape.update(place_on_positive_side(band.right_band, start=0))
    return outer_tape


def test_first_lowered_fragments_smoke() -> None:
    rows = lowering_smoke_rows(load_fixture("incrementer"))
    got = {row[0]: row[1:] for row in rows}

    assert got["HALT"][:2] == ["halted", "U_HALT"]
    assert got["GOTO"][:2] == ["stuck", "TARGET"]
    assert got["BRANCH_CMP"][:2] == ["stuck", "NEQ"]
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
    alphabet = sorted(set(band.linear()) | {"0", "1"})
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
