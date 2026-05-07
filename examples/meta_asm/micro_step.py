"""Run a hand-written Meta-ASM micro-step on an encoded UTM tape.

This example is intentionally smaller than the generated universal
interpreter. It shows that Meta-ASM is not general-purpose assembly; the
instructions know how to walk the encoded UTM band grammar.
"""

from __future__ import annotations

from mtm import Compiler, R, SourceTape, TMInstance, TMProgram
from mtm.lowering import ACTIVE_RULE, lower_program_to_raw_tm
from mtm.meta_asm import (
    Block,
    BranchAt,
    BranchCmp,
    CompareGlobalGlobal,
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
    Program,
    format_program,
)
from mtm.pretty import pretty_registers, pretty_tape
from mtm.raw_transition_tm import run_raw_tm
from mtm.semantic_objects import decoded_view_from_encoded_tape, start_head_from_encoded_tape
from mtm.utm_band_layout import (
    CUR_STATE,
    CUR_SYMBOL,
    END_RULES,
    EncodedTape,
    LEFT_DIR,
    MOVE,
    MOVE_DIR,
    NEXT,
    NEXT_STATE,
    READ,
    RIGHT_DIR,
    STATE,
    WRITE,
    WRITE_SYMBOL,
    split_runtime_tape,
)


def build_source_instance() -> TMInstance:
    blank = "_"
    return TMInstance(
        program=TMProgram(
            {
                ("q0", "A"): ("qH", "B", R),
            },
            initial_state="q0",
            halt_state="qH",
            blank=blank,
        ),
        tape=SourceTape(right_band=("A", "C", blank), head=0, blank=blank),
        initial_state="q0",
        halt_state="qH",
    )


def build_micro_step_program(encoded_tape: EncodedTape) -> Program:
    encoding = encoded_tape.encoding
    # These instructions do not compare or copy source symbols directly. They
    # walk encoded fields on the UTM band, so the hand-written ASM must pass the
    # active ABI widths explicitly: state operations get state_width, symbol
    # operations get symbol_width, and direction operations get direction_width.
    # That coupling is the main point of the example.
    return Program(
        entry_label="FIND_HEAD",
        blocks=(
            Block(
                "FIND_HEAD",
                (
                    FindHeadCell(),
                    CopyHeadSymbolTo(CUR_SYMBOL, encoding.symbol_width),
                    FindFirstRule(),
                    Goto("LOOKUP_RULE"),
                ),
            ),
            Block("LOOKUP_RULE", (BranchAt(END_RULES, "STUCK", "CHECK_STATE"),)),
            Block(
                "CHECK_STATE",
                (
                    CompareGlobalLocal(CUR_STATE, STATE, encoding.state_width),
                    BranchCmp("CHECK_READ", "NEXT_RULE"),
                ),
            ),
            Block(
                "CHECK_READ",
                (
                    CompareGlobalLocal(CUR_SYMBOL, READ, encoding.symbol_width),
                    BranchCmp("MATCHED_RULE", "NEXT_RULE"),
                ),
            ),
            Block("NEXT_RULE", (FindNextRule(), Goto("LOOKUP_RULE"))),
            Block(
                "MATCHED_RULE",
                (
                    CopyLocalGlobal(WRITE, WRITE_SYMBOL, encoding.symbol_width),
                    CopyLocalGlobal(NEXT, NEXT_STATE, encoding.state_width),
                    CopyLocalGlobal(MOVE, MOVE_DIR, encoding.direction_width),
                    FindHeadCell(),
                    CopyGlobalToHeadSymbol(WRITE_SYMBOL, encoding.symbol_width),
                    CopyGlobalGlobal(NEXT_STATE, CUR_STATE, encoding.state_width),
                    Goto("DISPATCH_MOVE"),
                ),
            ),
            Block(
                "DISPATCH_MOVE",
                (
                    CompareGlobalGlobal(MOVE_DIR, RIGHT_DIR, encoding.direction_width),
                    BranchCmp("MOVE_RIGHT", "CHECK_LEFT"),
                ),
            ),
            Block(
                "CHECK_LEFT",
                (
                    CompareGlobalGlobal(MOVE_DIR, LEFT_DIR, encoding.direction_width),
                    BranchCmp("MOVE_LEFT", "DONE"),
                ),
            ),
            Block("MOVE_RIGHT", (FindHeadCell(), MoveSimHeadRight(encoding.symbol_width), Halt())),
            Block("MOVE_LEFT", (FindHeadCell(), MoveSimHeadLeft(encoding.symbol_width), Halt())),
            Block("DONE", (Halt(),)),
            Block("STUCK", (Halt(),)),
        ),
    )


def print_decoded_state(title: str, encoded_tape: EncodedTape) -> None:
    view = decoded_view_from_encoded_tape(encoded_tape)
    print(title)
    print(f"  current state: {view.current_state}")
    print(f"  simulated head: {view.simulated_head}")
    print("  registers:")
    print(pretty_registers(encoded_tape.encoding, encoded_tape.left_band).replace("\n", "\n    "))
    print("  simulated tape:")
    print("    " + pretty_tape(encoded_tape.encoding, encoded_tape.right_band).replace("\n", "\n    "))
    print()


def main() -> int:
    encoded = Compiler().compile(build_source_instance())
    encoded_tape = encoded.to_encoded_tape()
    program = build_micro_step_program(encoded_tape)
    alphabet = sorted({*encoded_tape.linear(), "0", "1", ACTIVE_RULE})
    raw_tm = lower_program_to_raw_tm(program, alphabet)

    print("HAND-WRITTEN META-ASM")
    print(format_program(program))
    print()
    print(f"LOWERED RAW TM TRANSITIONS: {len(raw_tm.prog)}")
    print()
    print_decoded_state("BEFORE", encoded_tape)

    result = run_raw_tm(
        raw_tm,
        encoded_tape.runtime_tape,
        head=start_head_from_encoded_tape(encoded_tape),
        state=program.entry_label,
        max_steps=200_000,
    )
    final_left, final_right = split_runtime_tape(result["tape"])
    final_encoded_tape = EncodedTape(
        encoded_tape.encoding,
        final_left,
        final_right,
        minimal_abi=encoded_tape.minimal_abi,
        target_abi=encoded_tape.target_abi,
    )

    print(f"RAW RUN: status={result['status']} steps={result['steps']} head={result['head']}")
    print()
    print_decoded_state("AFTER", final_encoded_tape)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
