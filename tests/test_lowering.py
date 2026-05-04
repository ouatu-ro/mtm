from mtm import load_fixture
from mtm.lowering_checks import lowering_smoke_rows


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
