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
    return _status(session).splitlines()[0]


def _raw_steps_from_action(text: str) -> int:
    match = re.search(r"raw_steps=(\d+)", text)
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

    assert re.match(r"status: running raw_step=0 max_raw=100000 history=0/0", _compact_status_line(session))

    _step(session, "raw")
    _step(session, "raw")
    assert re.match(r"status: running raw_step=2 max_raw=100000 history=2/2", _compact_status_line(session))

    _back(session, "raw")
    compact = _compact_status_line(session)
    assert re.match(r"status: running raw_step=1 max_raw=100000 history=1/2", compact)


def test_session_where_renders_setup_for_entry_location() -> None:
    session, _ = _build_incrementer_session()
    where = _where(session)
    lines = where.splitlines()

    assert lines[0].startswith("where: block=START_STEP instruction=setup routine=0:seek op=0")
    assert lines[1].startswith("row: state='START_STEP' read='#CUR_STATE'")
    assert lines[2] == "instruction: SEEK #CUR_STATE L"


def test_session_view_reports_semantic_decode_and_unavailable_mode() -> None:
    decoded_session, _ = _build_incrementer_session(request_decode=True)
    undecoded_session, _ = _build_incrementer_session(request_decode=False)

    decoded = _view(decoded_session)
    undecoded = _view(undecoded_session)

    assert "semantic: state='qFindMargin'" in decoded
    assert "semantic: unavailable" in undecoded


def test_session_view_reports_semantic_decode_error_without_raising() -> None:
    band = load_fixture("incrementer").build_band()
    builder = TMBuilder(sorted(set(band.linear()) | {"0", "1"}), blank=band.encoding.blank)
    builder.emit("start", CUR_STATE, builder.halt_state, "0", S)
    runner = RawTraceRunner(builder.build("start"), band.runtime_tape, head=start_head_from_encoded_band(band))
    runner.step()

    session = _build_session(runner, encoding=band.encoding)
    text = _view(session)

    assert "semantic: <decode error:" in text


def test_session_step_raw_and_back_raw_report_rewound_and_at_start() -> None:
    program = Program(blocks=(Block("ENTRY", (Goto("DONE"),)),), entry_label="ENTRY")
    lowered = lower_program_with_source_map(program, ("0", RULES))
    runner = RawTraceRunner(lowered.raw_program, {0: "0", 1: "0"}, head=0, state="ENTRY")
    session = _build_session(runner, encoding=None)

    stepped = _step(session, "raw")
    assert stepped.startswith("step raw: status=stepped raw_steps=1")

    rewound = _back(session, "raw")
    assert rewound.startswith("back raw: status=rewound raw_steps=1")

    at_start = _back(session, "raw")
    assert at_start.startswith("back raw: status=at_start raw_steps=0")


def test_session_step_instruction_runs_rows_and_honors_group_max_raw_guard() -> None:
    runner = _build_meta_session_for_block_step()
    session = _build_session(runner, max_raw=100000)

    first = _step(session, "instruction")
    assert first.startswith("step instruction: status=stepped")
    assert _raw_steps_from_action(first) > 0
    assert "where:" in first

    session_guarded = _build_session(_build_meta_session_for_block_step(), max_raw=1)
    guarded = _step(session_guarded, "instruction")
    assert guarded.startswith("step instruction: status=max_raw raw_steps=1")


def test_session_back_instruction_rewinds_to_previous_segment_not_previous_row() -> None:
    runner = _build_meta_session_for_block_step()
    session = _build_session(runner, max_raw=100000)

    first = _step(session, "instruction")
    assert first.startswith("step instruction: status=stepped")

    rewound = _back(session, "instruction")
    assert rewound.startswith("back instruction: status=rewound")

    snapshot_line = rewound.splitlines()[1]
    assert "snapshot: raw_step=0" in snapshot_line

    at_start = _back(session, "instruction")
    assert at_start.startswith("back instruction: status=at_start raw_steps=0")
