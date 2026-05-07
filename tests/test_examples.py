from examples.meta_asm.micro_step import main as micro_step_main


def test_meta_asm_micro_step_example(capsys) -> None:
    assert micro_step_main() == 0
    output = capsys.readouterr().out

    assert "HAND-WRITTEN META-ASM" in output
    assert "COPY_HEAD_SYMBOL_TO #CUR_SYMBOL" in output
    assert "LOWERED RAW TM TRANSITIONS: 21501" in output
    assert "RAW RUN: status=halted steps=2301" in output
    assert "current state: qH" in output
    assert "B C _" in output
