blank = "_"
initial_state = "qFindMargin"
halt_state = "qDone"
input_string = "1011"
blanks_right = 4
note = "Binary increment by one."

tm_program = {
    ("qFindMargin", "0"): ("qFindMargin", "0", R),
    ("qFindMargin", "1"): ("qFindMargin", "1", R),
    ("qFindMargin", blank): ("qAdd", blank, L),
    ("qAdd", "0"): ("qDone", "1", L),
    ("qAdd", "1"): ("qAdd", "0", L),
    ("qAdd", blank): ("qDone", "1", L),
}
