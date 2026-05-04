"""Binary incrementer fixture."""

from __future__ import annotations

from ..tape_encoding import L, R
from . import TMFixture

blank = "_"
fixture = TMFixture(
    name="incrementer",
    tm_program={
        # qFindMargin: scan right to the end of the input.
        ("qFindMargin", "0"): ("qFindMargin", "0", R),
        ("qFindMargin", "1"): ("qFindMargin", "1", R),
        ("qFindMargin", blank): ("qAdd", blank, L),

        # qAdd: add 1 with carry while moving left.
        ("qAdd", "0"): ("qDone", "1", L),
        ("qAdd", "1"): ("qAdd", "0", L),
        ("qAdd", blank): ("qDone", "1", L),
    },
    input_symbols=list("1011"),
    initial_state="qFindMargin",
    halt_state="qDone",
    blank=blank,
    blanks_left=0,
    blanks_right=4,
    note="Binary increment by one.",
)
