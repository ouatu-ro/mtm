from __future__ import annotations

from mtm import load_fixture
from mtm.debugger import DebuggerPresenter, DebuggerSession, PlainTextRenderer, RawTraceRunner
from mtm.lowering import ACTIVE_RULE, lower_program_with_source_map
from mtm.meta_asm import build_universal_meta_asm
from mtm.semantic_objects import start_head_from_encoded_band


def _build_session() -> DebuggerSession:
    band = load_fixture("incrementer").build_band()
    program = build_universal_meta_asm(band.encoding)
    alphabet = sorted(set(band.linear()) | {"0", "1", ACTIVE_RULE})
    lowered = lower_program_with_source_map(program, alphabet)
    runner = RawTraceRunner(
        lowered.raw_program,
        band.runtime_tape,
        head=start_head_from_encoded_band(band),
        state=program.entry_label,
        source_map=lowered.source_map,
    )
    return DebuggerSession(runner, encoding=band.encoding)


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
