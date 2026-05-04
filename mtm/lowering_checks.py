"""Shared smoke checks for the first lowered raw-TM fragments."""

from __future__ import annotations

from .fixtures import TMFixture
from .lowering import lower_instruction
from .meta_asm import BranchCmp, Goto, Halt, WriteGlobal, bits
from .outer_tape import CMP_FLAG, CUR_SYMBOL, split_outer_tape
from .raw_tm import TMBuilder, run_raw_tm


def lowering_smoke_rows(fixture: TMFixture) -> list[list[object]]:
    band = fixture.build_band()
    left_band = band.left_band
    left_addresses = list(range(-len(left_band), 0))
    address_of = lambda marker: left_addresses[left_band.index(marker)]
    alphabet = sorted(set(band.linear()) | {"0", "1"})
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
    return rows


__all__ = ["lowering_smoke_rows"]
