from __future__ import annotations

import re

from mtm import load_fixture
from mtm.debugger import DebuggerPresenter, DebuggerSession, PlainTextRenderer, RawTraceRunner, RichRenderer
from mtm.lowering import ACTIVE_RULE, lower_program_with_source_map
from mtm.meta_asm import build_universal_meta_asm
from mtm.semantic_objects import start_head_from_encoded_tape


def _build_session() -> DebuggerSession:
    tape = load_fixture("incrementer").build_tape()
    program = build_universal_meta_asm(tape.encoding)
    alphabet = sorted(set(tape.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        tape.runtime_tape,
        head=start_head_from_encoded_tape(tape),
        state=program.entry_label,
        source_map=lowered.source_map,
    )
    return DebuggerSession(runner, encoding=tape.encoding)


def test_presenter_status_doc_exposes_block_structure() -> None:
    session = _build_session()
    document = DebuggerPresenter().status_doc(session.status())

    assert document.kind == "status"
    assert [block.kind for block in document.blocks] == ["status", "record", "record", "instruction"]
    assert document.blocks[1].title == "RAW"
    assert document.blocks[2].title == "SOURCE"
    assert document.blocks[3].title == "INSTRUCTION"


def test_plain_text_renderer_renders_help_overview_from_presenter() -> None:
    text = PlainTextRenderer().render(DebuggerPresenter().help_doc(None))

    assert "MTM debugger" in text
    assert "Command" in text
    assert "step raw [N]" in text
    assert "Visual Legend:" in text
    assert "INSTRUCTION  OPCODE <ARGS>" in text
    assert "Fields:" in text


def test_plain_text_renderer_renders_topic_help_with_usage() -> None:
    text = PlainTextRenderer().render(DebuggerPresenter().help_doc("step raw"))

    assert "step raw" in text
    assert "usage: step raw [N]" in text
    assert "alias: s" in text
    assert "Advance by exactly one raw TM transition." in text
    assert "Output:" in text


def test_rich_renderer_adds_ansi_styles_for_interactive_output(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    session = _build_session()
    document = DebuggerPresenter().action_doc(session.step_many("raw", 1))

    rendered = RichRenderer(color=True).render(document)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", rendered)

    assert "\x1b[" in rendered
    assert "step raw" in plain
    assert "COMPARE_GLOBAL_GLOBAL #CUR_STATE #HALT_STATE 2" in plain
