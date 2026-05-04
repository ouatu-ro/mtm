"""Shared smoke checks for the first lowered raw-TM fragments."""

from __future__ import annotations

from .fixtures import TMFixture
from .lowering import ACTIVE_RULE, lower_instruction
from .meta_asm import (
    BranchAt,
    BranchCmp,
    CompareGlobalLiteral,
    CompareGlobalLocal,
    CopyGlobalGlobal,
    CopyGlobalToHeadSymbol,
    CopyHeadSymbolTo,
    CopyLocalGlobal,
    FindFirstRule,
    FindHeadCell,
    FindNextRule,
    Goto,
    Halt,
    MoveSimHeadLeft,
    MoveSimHeadRight,
    Seek,
    SeekOneOf,
    WriteGlobal,
    bits,
)
from .compiled_band import CELL, CMP_FLAG, CUR_STATE, CUR_SYMBOL, END_RULES, HEAD, NO_HEAD, READ, RULE, RULES, STATE, WRITE, WRITE_SYMBOL, materialize_raw_tape, split_outer_tape
from .raw_tm import TMBuilder, run_raw_tm


def set_global_bits(band, marker: str, value: str):
    left_band = list(band.left_band)
    start = left_band.index(marker) + 1
    left_band[start:start + len(value)] = list(value)
    return materialize_raw_tape(left_band, band.right_band)


def set_head_cell(band, cell_index: int):
    span = 3 + band.encoding.symbol_width
    right_band = list(band.right_band)
    for index, token in enumerate(right_band):
        if token in {HEAD, NO_HEAD}:
            right_band[index] = NO_HEAD
    right_band[1 + cell_index * span + 1] = HEAD
    return materialize_raw_tape(band.left_band, right_band)


def lowering_smoke_rows(fixture: TMFixture) -> list[list[object]]:
    band = fixture.build_band()
    left_band = band.left_band
    left_addresses = list(range(-len(left_band), 0))
    address_of = lambda marker: left_addresses[left_band.index(marker)]
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    rows: list[list[object]] = []

    builder = TMBuilder(alphabet)
    lower_instruction(builder, Halt(), state="start", continuation_label="NEXT")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=0, max_steps=5)
    rows.append(["HALT", result["status"], result["state"], result["head"], "-"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, Goto("TARGET"), state="start", continuation_label="NEXT")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=0, max_steps=5)
    rows.append(["GOTO", result["status"], result["state"], result["head"], "-"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, BranchCmp("EQ", "NEQ"), state="start", continuation_label="NEXT")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(CMP_FLAG), max_steps=5)
    rows.append(["BRANCH_CMP", result["status"], result["state"], result["head"], "cmp=0 -> NEQ"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, BranchAt(RULE, "YES", "NO"), state="start", continuation_label="NEXT")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(RULE), max_steps=5)
    rows.append(["BRANCH_AT", result["status"], result["state"], result["head"], f"{RULE} -> YES"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, WriteGlobal(CUR_SYMBOL, bits("01")), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(CUR_SYMBOL), max_steps=10)
    final_left_band, _ = split_outer_tape(result["tape"])
    cur_symbol_index = final_left_band.index(CUR_SYMBOL)
    rows.append([
        "WRITE_GLOBAL",
        result["status"],
        result["state"],
        result["head"],
        f"{CUR_SYMBOL}={''.join(final_left_band[cur_symbol_index + 1:cur_symbol_index + 3])}",
    ])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, Seek(RULES, "L"), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=0, max_steps=300)
    rows.append(["SEEK", result["status"], result["state"], result["head"], f"at {RULES}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, SeekOneOf((RULE, END_RULES), "R"), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(RULES), max_steps=300)
    rows.append(["SEEK_ONE_OF", result["status"], result["state"], result["head"], f"at {RULE}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, FindFirstRule(), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=0, max_steps=300)
    rows.append(["FIND_FIRST_RULE", result["status"], result["state"], result["head"], f"at {RULE}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, FindNextRule(), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(RULE), max_steps=300)
    rows.append(["FIND_NEXT_RULE", result["status"], result["state"], result["head"], f"after first {RULE}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, FindHeadCell(), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=0, max_steps=300)
    rows.append(["FIND_HEAD_CELL", result["status"], result["state"], result["head"], "at head #CELL"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, MoveSimHeadRight(), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=1, max_steps=200)
    rows.append(["MOVE_SIM_HEAD_RIGHT", result["status"], result["state"], result["head"], "head moved to next cell"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, MoveSimHeadLeft(), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), set_head_cell(band, 1), head=1 + (3 + band.encoding.symbol_width), max_steps=200)
    rows.append(["MOVE_SIM_HEAD_LEFT", result["status"], result["state"], result["head"], "head moved to previous cell"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, CopyLocalGlobal(WRITE, WRITE_SYMBOL, 2), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(RULE), max_steps=500)
    final_left_band, _ = split_outer_tape(result["tape"])
    write_symbol_index = final_left_band.index(WRITE_SYMBOL)
    rows.append(["COPY_LOCAL_GLOBAL", result["status"], result["state"], result["head"], f"{WRITE_SYMBOL}={''.join(final_left_band[write_symbol_index + 1:write_symbol_index + 3])}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, CopyGlobalGlobal(WRITE_SYMBOL, CUR_SYMBOL, 2), state="start", continuation_label="DONE")
    prepared_tape = set_global_bits(band, WRITE_SYMBOL, "01")
    result = run_raw_tm(builder.build("start"), prepared_tape, head=address_of(WRITE_SYMBOL), max_steps=500)
    final_left_band, _ = split_outer_tape(result["tape"])
    cur_symbol_index = final_left_band.index(CUR_SYMBOL)
    rows.append(["COPY_GLOBAL_GLOBAL", result["status"], result["state"], result["head"], f"{CUR_SYMBOL}={''.join(final_left_band[cur_symbol_index + 1:cur_symbol_index + 3])}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, CopyHeadSymbolTo(CUR_SYMBOL, 2), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=1, max_steps=500)
    final_left_band, _ = split_outer_tape(result["tape"])
    cur_symbol_index = final_left_band.index(CUR_SYMBOL)
    rows.append(["COPY_HEAD_SYMBOL_TO", result["status"], result["state"], result["head"], f"{CUR_SYMBOL}={''.join(final_left_band[cur_symbol_index + 1:cur_symbol_index + 3])}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, CopyGlobalToHeadSymbol(WRITE_SYMBOL, 2), state="start", continuation_label="DONE")
    prepared_tape = set_global_bits(band, WRITE_SYMBOL, "00")
    result = run_raw_tm(builder.build("start"), prepared_tape, head=1, max_steps=1500)
    _, final_right_band = split_outer_tape(result["tape"])
    rows.append(["COPY_GLOBAL_TO_HEAD_SYMBOL", result["status"], result["state"], result["head"], f"head_symbol={''.join(final_right_band[3:5])}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, CompareGlobalLiteral(CUR_STATE, bits("10")), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(CUR_STATE), max_steps=500)
    final_left_band, _ = split_outer_tape(result["tape"])
    cmp_index = final_left_band.index(CMP_FLAG)
    rows.append(["COMPARE_GLOBAL_LITERAL", result["status"], result["state"], result["head"], f"{CMP_FLAG}={final_left_band[cmp_index + 1]}"])

    builder = TMBuilder(alphabet)
    lower_instruction(builder, CompareGlobalLocal(CUR_STATE, STATE, 2), state="start", continuation_label="DONE")
    result = run_raw_tm(builder.build("start"), dict(band.outer_tape), head=address_of(RULE), max_steps=1000)
    final_left_band, _ = split_outer_tape(result["tape"])
    cmp_index = final_left_band.index(CMP_FLAG)
    rows.append(["COMPARE_GLOBAL_LOCAL", result["status"], result["state"], result["head"], f"{CMP_FLAG}={final_left_band[cmp_index + 1]}"])
    return rows


__all__ = ["lowering_smoke_rows"]
