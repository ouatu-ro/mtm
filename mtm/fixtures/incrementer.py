"""Binary incrementer fixture."""

from __future__ import annotations

from ..semantic_objects import TMBand
from ..source_encoding import L, R, TMProgram
from . import TMFixture

blank = "_"
fixture = TMFixture(
    name="incrementer",
    tm_program=TMProgram({
        # qFindMargin: scan right to the end of the input.
        ("qFindMargin", "0"): ("qFindMargin", "0", R),
        ("qFindMargin", "1"): ("qFindMargin", "1", R),
        ("qFindMargin", blank): ("qAdd", blank, L),

        # qAdd: add 1 with carry while moving left.
        ("qAdd", "0"): ("qDone", "1", L),
        ("qAdd", "1"): ("qAdd", "0", L),
        ("qAdd", blank): ("qDone", "1", L),
    }, initial_state="qFindMargin", halt_state="qDone", blank=blank),
    band=TMBand(right_band=tuple("1011____"), head=0, blank=blank),
    initial_state="qFindMargin",
    halt_state="qDone",
    note="Binary increment by one.",
)
