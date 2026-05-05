from __future__ import annotations

import re

from mtm import load_fixture
from mtm.debugger import RawTraceRunner
from mtm.lowering import lower_program_with_source_map
from mtm.lowering.constants import ACTIVE_RULE
from mtm.meta_asm import Block, Goto, Program, Seek, build_universal_meta_asm
from mtm.raw_transition_tm import S, TMBuilder
from mtm.semantic_objects import start_head_from_encoded_band
from mtm.source_encoding import Encoding
from mtm.utm_band_layout import CUR_STATE, RULES

try:
    from mtm.debugger import DebuggerSession
except ImportError:  # pragma: no cover - compatibility shim if session is exported from a submodule
    from mtm.debugger.session import DebuggerSession


def _build_session(
    runner: RawTraceRunner,
    *,
    encoding: Encoding | None = None,
    max_raw: int = 100000,
) -> DebuggerSession:
    candidates = [
        {"runner": runner, "encoding": encoding, "max_raw": max_raw},
        {"runner": runner, "encoding": encoding},
        {"runner": runner, "max_raw": max_raw},
        {"runner": runner},
        {"trace_runner": runner, "encoding": encoding, "max_raw": max_raw},
        {"trace_runner": runner, "encoding": encoding},
        {"trace_runner": runner},
        {"runner": runner, "max_raw_steps": max_raw},
        {"trace_runner": runner, "max_raw_steps": max_raw},
    ]
    for kwargs in candidates:
        try:
            return DebuggerSession(**kwargs)
        except TypeError:
            pass
    return DebuggerSession(runner, encoding=encoding, max_raw=max_raw)


def _call_no_args(session: DebuggerSession, names: tuple[str, ...]) -> str:
    for name in names:
        member = getattr(session, name, None)
        if member is None:
            continue
        if callable(member):
            value = member()
        else:
            value = member
        return str(value)
    raise AssertionError(f"missing session method (tried: {', '.join(names)})")


def _call_with_boundary(session: DebuggerSession, names: tuple[str, ...], boundary: str) -> str:
    for name in names:
        member = getattr(session, name, None)
        if member is None:
            continue
        value = member(boundary)
        return str(value)
    raise AssertionError(f"missing session command method (tried: {', '.join(names)})")


def _status(session: DebuggerSession) -> str:
    return _call_no_args(session, ("status_text", "status"))


def _where(session: DebuggerSession) -> str:
    return _call_no_args(session, ("where_text", "where"))


def _view(session: DebuggerSession) -> str:
    return _call_no_args(session, ("view_text", "view"))


def _step(session: DebuggerSession, boundary: str) -> str:
    return _call_with_boundary(session, ("step_text", "step"), boundary)


def _back(session: DebuggerSession, boundary: str) -> str:
    return _call_with_boundary(session, ("back_text", "back"), boundary)


def _compact_status_line(session: DebuggerSession) -> str:
    return _status(session)


def _raw_steps_from_action(text: str) -> int:
    match = re.search(r"raw_delta=([+-]?\d+)", text)
    assert match is not None
    return int(match.group(1))


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
    session = _build_session(
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


def test_session_status_includes_cursor_latest_and_max_raw() -> None:
    session, _ = _build_incrementer_session()

    initial = _compact_status_line(session)
    assert initial.splitlines()[0] == "running  raw=0  max_raw=100000  hist=0/0"
    assert initial.splitlines()[1] == "RAW          raw=0  head=-155  read='#CUR_STATE'  state=START_STEP"
    assert initial.splitlines()[2] == "SOURCE       block=START_STEP  instr=setup  routine=0:seek  op=0"
    assert initial.splitlines()[3] == "INSTRUCTION  SEEK #CUR_STATE L"

    _step(session, "raw")
    _step(session, "raw")
    after_steps = _compact_status_line(session)
    assert after_steps.splitlines()[0] == "running  raw=2  max_raw=100000  hist=2/2"

    _back(session, "raw")
    compact = _compact_status_line(session)
    assert compact.splitlines()[0] == "running  raw=1  max_raw=100000  hist=1/2"


def test_session_where_renders_setup_for_entry_location() -> None:
    session, _ = _build_incrementer_session()
    where = _where(session)
    lines = where.splitlines()
    assert lines[0] == "SOURCE       block=START_STEP  instr=setup  routine=0:seek  op=0"
    assert lines[1] == "INSTRUCTION  SEEK #CUR_STATE L"
    assert lines[2] == "             Move L until marker #CUR_STATE is under the head."
    assert lines[3].startswith("NEXT ROW     state=START_STEP  read='#CUR_STATE'")


def test_session_view_reports_semantic_decode_and_unavailable_mode() -> None:
    decoded_session, _ = _build_incrementer_session(request_decode=True)
    undecoded_session, _ = _build_incrementer_session(request_decode=False)

    decoded = _view(decoded_session)
    undecoded = _view(undecoded_session)

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

    session = _build_session(runner, encoding=band.encoding)
    text = _view(session)

    assert "SEMANTIC     <decode error:" in text


def test_session_step_raw_and_back_raw_report_rewound_and_at_start() -> None:
    program = Program(blocks=(Block("ENTRY", (Goto("DONE"),)),), entry_label="ENTRY")
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(lowered.raw_program, {0: "0", 1: "0"}, head=0, state="ENTRY")
    session = _build_session(runner, encoding=None)

    stepped = _step(session, "raw")
    assert stepped.splitlines()[0] == "step raw  stepped  raw_delta=+1"
    assert stepped.splitlines()[1] == "RAW          raw=1  head=0  read='0'  state=DONE"

    rewound = _back(session, "raw")
    assert rewound.splitlines()[0] == "back raw  rewound  raw_delta=-1"

    at_start = _back(session, "raw")
    assert at_start.splitlines()[0] == "back raw  at_start  raw_delta=0"


def test_session_step_and_back_support_repeat_counts() -> None:
    session, _ = _build_incrementer_session()

    stepped = session.step_many_text("raw", 3)
    assert stepped.splitlines()[0] == "step raw  stepped  count=3  raw_delta=+3"
    assert stepped.splitlines()[1].startswith("RAW          raw=3")

    rewound = session.back_many_text("raw", 2)
    assert rewound.splitlines()[0] == "back raw  rewound  count=2  raw_delta=-2"
    assert rewound.splitlines()[1].startswith("RAW          raw=1")

    at_start = session.back_many_text("raw", 5)
    assert at_start.splitlines()[0] == "back raw  at_start  count=1/5  raw_delta=-1"
    assert at_start.splitlines()[1].startswith("RAW          raw=0")


def test_session_step_instruction_runs_rows_and_honors_group_max_raw_guard() -> None:
    runner = _build_meta_session_for_block_step()
    session = _build_session(runner, max_raw=100000)

    first = _step(session, "instruction")
    assert first.startswith("step instruction  stepped  raw_delta=+")
    assert _raw_steps_from_action(first) > 0
    assert "SOURCE       block=ENTRY  instr=1  routine=1:goto  op=0" in first
    assert "INSTRUCTION  GOTO SECOND" in first
    assert "             Jump to block SECOND." in first

    session_guarded = _build_session(_build_meta_session_for_block_step(), max_raw=1)
    guarded = _step(session_guarded, "instruction")
    assert guarded.splitlines()[0] == "step instruction  max_raw  raw_delta=+1"

    repeated_guarded = session_guarded.step_many_text("instruction", 3)
    assert repeated_guarded.splitlines()[0] == "step instruction  max_raw  count=0/3  raw_delta=+1"


def test_session_back_instruction_rewinds_to_previous_segment_not_previous_row() -> None:
    runner = _build_meta_session_for_block_step()
    session = _build_session(runner, max_raw=100000)

    first = _step(session, "instruction")
    assert first.startswith("step instruction  stepped")

    rewound = _back(session, "instruction")
    assert rewound.splitlines()[0].startswith("back instruction  rewound  raw_delta=-")
    assert "RAW          raw=0  head=0  read='0'  state=ENTRY" in rewound

    at_start = _back(session, "instruction")
    assert at_start.splitlines()[0] == "back instruction  at_start  raw_delta=0"
