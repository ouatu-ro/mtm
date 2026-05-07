blank = "_"
initial_state = "q0"
halt_state = "qH"
tape = SourceTape(right_band=(blank,), head=0, blank=blank)
note = "Move right once, left three times, write C at -1, then halt at -2."

tm_program = TMProgram({
    ("q0", blank): ("q1", "A", R),
    ("q1", blank): ("q2", "B", L),
    ("q2", "A"): ("q3", "A", L),
    ("q3", blank): ("qH", "C", L),
}, initial_state=initial_state, halt_state=halt_state, blank=blank)
