format = 'mtm-raw-tm-v1'
start_state = 'q0'
halt_state = 'qH'
blank = '_'
alphabet = ['_', 'A', 'B', 'C']
raw_tm = {
    ('q0', '_'): ('q1', 'A', 1),
    ('q1', '_'): ('q2', 'B', -1),
    ('q2', 'A'): ('q3', 'A', -1),
    ('q3', '_'): ('qH', 'C', -1),
}
