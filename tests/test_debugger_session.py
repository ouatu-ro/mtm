from __future__ import annotations

from mtm import load_fixture
from mtm.debugger import DebuggerPresenter, DebuggerSession, PlainTextRenderer, RawTraceRunner
from mtm.lowering import lower_program_with_source_map
from mtm.lowering.constants import ACTIVE_RULE
from mtm.meta_asm import Block, Goto, Program, Seek, build_universal_meta_asm
from mtm.raw_transition_tm import S, TMBuilder
from mtm.semantic_objects import start_head_from_encoded_band
from mtm.source_encoding import Encoding
from mtm.utm_band_layout import CUR_STATE, RULES


def _render_status(session: DebuggerSession) -> str:
    return PlainTextRenderer().render(DebuggerPresenter().status_doc(session.status()))


def _render_where(session: DebuggerSession) -> str:
    return PlainTextRenderer().render(DebuggerPresenter().where_doc(session.where()))


def _render_view(session: DebuggerSession) -> str:
    return PlainTextRenderer().render(DebuggerPresenter().view_doc(session.view()))


def _render_action(action_row) -> str:
    return PlainTextRenderer().render(DebuggerPresenter().action_doc(action_row))


def _raw_delta(text: str) -> int:
    for part in text.split():
        if part.startswith("raw_delta="):
            return int(part.split("=", 1)[1])
    raise AssertionError("missing raw_delta")


def _build_incrementer_session(
    *,
    request_decode: bool = False,
    max_raw: int = 100000,
) -> tuple[DebuggerSession, object]:
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
    session = DebuggerSession(
        runner,
        encoding=band.encoding if request_decode else None,
        max_raw=max_raw,
    )
    return session, band


def _build_meta_session_for_block_step() -> RawTraceRunner:
    program = Program(
        blocks=(
            Block("ENTRY", (Seek(RULES, "R"), Goto("SECOND"))),
            Block("SECOND", (Goto("DONE"),)),
        ),
        entry_label="ENTRY",
    )
    lowered = lower_program_with_source_map(program, ("0", RULES))
    return RawTraceRunner(
        lowered.raw_program,
        {0: "0", 1: "0", 2: RULES},
        head=0,
        state="ENTRY",
        source_map=lowered.source_map,
    )


def test_session_status_query_and_render_include_cursor_latest_and_max_raw() -> None:
    session, _ = _build_incrementer_session()

    status = session.status()
    assert status.snapshot.run_status == "running"
    assert status.snapshot.raw == 0
    assert status.snapshot.max_raw == 100000
    assert status.snapshot.hist_current == 0
    assert status.snapshot.hist_last == 0
    assert status.source.block == "START_STEP"
    assert status.source.instr == "0"
    assert status.source.routine == "0:compare_global_global"

    rendered = _render_status(session)
    assert rendered.splitlines()[0] == "running  raw=0  max_raw=100000  hist=0/0"
    assert rendered.splitlines()[1] == "RAW          raw=0  head=-169  read='#CUR_STATE'  state=START_STEP"
    assert rendered.splitlines()[2] == "SOURCE       block=START_STEP  instr=0  routine=0:compare_global_global  op=0"
    assert rendered.splitlines()[3] == "INSTRUCTION  COMPARE_GLOBAL_GLOBAL #CUR_STATE #HALT_STATE 2"

    session.step_many("raw", 2)
    session.back_many("raw", 1)
    status = session.status()
    assert status.snapshot.raw == 1
    assert status.snapshot.hist_current == 1
    assert status.snapshot.hist_last == 2


def test_session_where_renders_setup_for_entry_location() -> None:
    session, _ = _build_incrementer_session()
    where = _render_where(session)
    lines = where.splitlines()
    assert lines[0] == "SOURCE       block=START_STEP  instr=0  routine=0:compare_global_global  op=0"
    assert lines[1] == "INSTRUCTION  COMPARE_GLOBAL_GLOBAL #CUR_STATE #HALT_STATE 2"
    assert lines[2] == "             Compare register #CUR_STATE against register #HALT_STATE over 2 bits."
    assert lines[3].startswith("NEXT ROW     state=START_STEP  read='#CUR_STATE'")


def test_session_view_reports_semantic_decode_and_unavailable_mode() -> None:
    decoded_session, _ = _build_incrementer_session(request_decode=True)
    undecoded_session, _ = _build_incrementer_session(request_decode=False)

    decoded = _render_view(decoded_session)
    undecoded = _render_view(undecoded_session)

    assert "SEMANTIC     state=qFindMargin  head=0  symbol='1'" in decoded
    assert "SEM TAPE" in decoded
    assert "REGS         cur=qFindMargin" in decoded
    assert undecoded.endswith("SEMANTIC     unavailable")


def test_session_view_reports_semantic_decode_error_without_raising() -> None:
    band = load_fixture("incrementer").build_band()
    builder = TMBuilder(sorted(set(band.linear()) | {"0", "1"}), blank=band.encoding.blank)
    builder.emit("start", CUR_STATE, builder.halt_state, "0", S)
    runner = RawTraceRunner(builder.build("start"), band.runtime_tape, head=start_head_from_encoded_band(band))
    runner.step()

    session = DebuggerSession(runner, encoding=band.encoding)
    text = _render_view(session)

    assert "SEMANTIC     <decode error:" in text


def test_session_step_raw_and_back_raw_report_rewound_and_at_start() -> None:
    program = Program(blocks=(Block("ENTRY", (Goto("DONE"),)),), entry_label="ENTRY")
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(lowered.raw_program, {0: "0", 1: "0"}, head=0, state="ENTRY")
    session = DebuggerSession(runner, encoding=None)

    stepped = _render_action(session.step_many("raw", 1))
    assert stepped.splitlines()[0] == "step raw  stepped  raw_delta=+1"
    assert stepped.splitlines()[1] == "RAW          raw=1  head=0  read='0'  state=DONE"

    rewound = _render_action(session.back_many("raw", 1))
    assert rewound.splitlines()[0] == "back raw  rewound  raw_delta=-1"

    at_start = _render_action(session.back_many("raw", 1))
    assert at_start.splitlines()[0] == "back raw  at_start  raw_delta=0"


def test_session_step_and_back_support_repeat_counts() -> None:
    session, _ = _build_incrementer_session()

    stepped = _render_action(session.step_many("raw", 3))
    assert stepped.splitlines()[0] == "step raw  stepped  count=3  raw_delta=+3"
    assert stepped.splitlines()[1].startswith("RAW          raw=3")

    rewound = _render_action(session.back_many("raw", 2))
    assert rewound.splitlines()[0] == "back raw  rewound  count=2  raw_delta=-2"
    assert rewound.splitlines()[1].startswith("RAW          raw=1")

    at_start = _render_action(session.back_many("raw", 5))
    assert at_start.splitlines()[0] == "back raw  at_start  count=1/5  raw_delta=-1"
    assert at_start.splitlines()[1].startswith("RAW          raw=0")


def test_session_step_instruction_runs_rows_and_honors_group_max_raw_guard() -> None:
    runner = _build_meta_session_for_block_step()
    session = DebuggerSession(runner, max_raw=100000)

    first = _render_action(session.step_many("instruction", 1))
    assert first.startswith("step instruction  stepped  raw_delta=+")
    assert _raw_delta(first.splitlines()[0]) > 0
    assert "SOURCE       block=ENTRY  instr=1  routine=1:goto  op=0" in first
    assert "INSTRUCTION  GOTO SECOND" in first
    assert "             Jump to block SECOND." in first

    session_guarded = DebuggerSession(_build_meta_session_for_block_step(), max_raw=1)
    guarded = _render_action(session_guarded.step_many("instruction", 1))
    assert guarded.splitlines()[0] == "step instruction  max_raw  raw_delta=+1"

    repeated_guarded = _render_action(session_guarded.step_many("instruction", 3))
    assert repeated_guarded.splitlines()[0] == "step instruction  max_raw  count=0/3  raw_delta=+1"


def test_session_back_instruction_rewinds_to_previous_segment_not_previous_row() -> None:
    runner = _build_meta_session_for_block_step()
    session = DebuggerSession(runner, max_raw=100000)

    first = _render_action(session.step_many("instruction", 1))
    assert first.startswith("step instruction  stepped")

    rewound = _render_action(session.back_many("instruction", 1))
    assert rewound.splitlines()[0].startswith("back instruction  rewound  raw_delta=-")
    assert "RAW          raw=0  head=0  read='0'  state=ENTRY" in rewound

    at_start = _render_action(session.back_many("instruction", 1))
    assert at_start.splitlines()[0] == "back instruction  at_start  raw_delta=0"
