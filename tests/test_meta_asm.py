from mtm.meta_asm import Block, BranchAt, BranchCmp, CompareGlobalLiteral, CompareGlobalLocal, CopyGlobalGlobal, CopyGlobalToHeadSymbol, CopyHeadSymbolTo, CopyLocalGlobal, FindFirstRule, FindHeadCell, FindNextRule, Goto, Halt, MoveSimHeadLeft, MoveSimHeadRight, Program, Seek, SeekOneOf, Unimplemented, WriteGlobal, bits, format_instruction, format_program


def test_format_instruction_preserves_all_current_spellings() -> None:
    cases = [
        (Goto("NEXT"), "GOTO NEXT"),
        (Halt(), "HALT"),
        (Seek("#MARK", "R"), "SEEK #MARK R"),
        (SeekOneOf(("#A", "#B"), "L"), "SEEK_ONE_OF [#A, #B] L"),
        (FindFirstRule(), "FIND_FIRST_RULE"),
        (FindNextRule(), "FIND_NEXT_RULE"),
        (FindHeadCell(), "FIND_HEAD_CELL"),
        (CompareGlobalLocal("#GLOBAL", "#LOCAL", 3), "COMPARE_GLOBAL_LOCAL #GLOBAL #LOCAL 3"),
        (CompareGlobalLiteral("#GLOBAL", bits("101")), "COMPARE_GLOBAL_LITERAL #GLOBAL 101"),
        (BranchCmp("EQ", "NEQ"), "BRANCH_CMP EQ NEQ"),
        (CopyLocalGlobal("#LOCAL", "#GLOBAL", 2), "COPY_LOCAL_GLOBAL #LOCAL #GLOBAL 2"),
        (CopyGlobalGlobal("#SRC", "#DST", 4), "COPY_GLOBAL_GLOBAL #SRC #DST 4"),
        (CopyHeadSymbolTo("#GLOBAL", 2), "COPY_HEAD_SYMBOL_TO #GLOBAL 2"),
        (CopyGlobalToHeadSymbol("#GLOBAL", 2), "COPY_GLOBAL_TO_HEAD_SYMBOL #GLOBAL 2"),
        (WriteGlobal("#GLOBAL", bits("00")), "WRITE_GLOBAL #GLOBAL 00"),
        (MoveSimHeadLeft(), "MOVE_SIM_HEAD_LEFT"),
        (MoveSimHeadRight(), "MOVE_SIM_HEAD_RIGHT"),
        (BranchAt("#MARK", "YES", "NO"), "BRANCH_AT #MARK YES NO"),
        (Unimplemented("later"), "UNIMPLEMENTED later"),
    ]

    for instruction, expected in cases:
        assert format_instruction(instruction) == expected


def test_format_program_uses_instruction_registry_output() -> None:
    program = Program(
        blocks=(
            Block("START", (Goto("NEXT"), Halt())),
            Block("NEXT", (SeekOneOf(("#A", "#B"), "R"),)),
        ),
        entry_label="START",
    )

    assert format_program(program) == (
        "LABEL START\n"
        "  GOTO NEXT\n"
        "  HALT\n\n"
        "LABEL NEXT\n"
        "  SEEK_ONE_OF [#A, #B] R"
    )
