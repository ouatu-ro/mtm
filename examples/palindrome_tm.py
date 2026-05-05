blank = "_"
mark = "X"
initial_state = "qStart"
halt_state = "qAccept"
band = TMBand.from_dict({-1: "1", 0: "0", 1: "1"}, head=-1, blank=blank)
note = "Binary palindrome check over source addresses -1, 0, and 1."

tm_program = TMProgram({
    ("qStart", mark): ("qStart", mark, R),
    ("qStart", blank): (halt_state, blank, R),
    ("qStart", "0"): ("qSeekRight0", mark, R),
    ("qStart", "1"): ("qSeekRight1", mark, R),

    ("qSeekRight0", "0"): ("qSeekRight0", "0", R),
    ("qSeekRight0", "1"): ("qSeekRight0", "1", R),
    ("qSeekRight0", mark): ("qSeekRight0", mark, R),
    ("qSeekRight0", blank): ("qCheck0", blank, L),

    ("qSeekRight1", "0"): ("qSeekRight1", "0", R),
    ("qSeekRight1", "1"): ("qSeekRight1", "1", R),
    ("qSeekRight1", mark): ("qSeekRight1", mark, R),
    ("qSeekRight1", blank): ("qCheck1", blank, L),

    ("qCheck0", mark): ("qCheck0", mark, L),
    ("qCheck0", "0"): ("qReturnLeft", mark, L),
    ("qCheck0", "1"): ("qReject", "1", R),
    ("qCheck0", blank): (halt_state, blank, R),

    ("qCheck1", mark): ("qCheck1", mark, L),
    ("qCheck1", "1"): ("qReturnLeft", mark, L),
    ("qCheck1", "0"): ("qReject", "0", R),
    ("qCheck1", blank): (halt_state, blank, R),

    ("qReturnLeft", "0"): ("qReturnLeft", "0", L),
    ("qReturnLeft", "1"): ("qReturnLeft", "1", L),
    ("qReturnLeft", mark): ("qReturnLeft", mark, L),
    ("qReturnLeft", blank): ("qStart", blank, R),
}, initial_state=initial_state, halt_state=halt_state, blank=blank)
