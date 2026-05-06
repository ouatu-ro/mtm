import mtm
from mtm import Compiler, L, R, TMAbi, TMBand, TMInstance, TMProgram, load_fixture, UniversalInterpreter
from mtm.artifacts import read_utm_artifact, write_utm_artifact
from mtm.lowering import lower_program_to_raw_tm
from mtm.meta_asm import CompareGlobalGlobal, build_universal_meta_asm
from mtm.pretty import pretty_runtime_tape
from mtm.raw_transition_tm import S, TMBuilder, TMTransitionProgram
from mtm.semantic_objects import RawTMInstance, SourceArtifact, UTMBandArtifact, UTMProgramArtifact, build_raw_guest_encoding, compile_raw_guest, decoded_view_from_encoded_band, encoded_band_from_utm_artifact, infer_minimal_abi, infer_raw_guest_minimal_abi, utm_artifact_from_band, utm_encoded_from_band
from mtm.source_encoding import abi_compatible, abi_from_literal, abi_to_literal, assert_abi_compatible
from mtm.utm_band_layout import BLANK_SYMBOL, HALT_STATE, LEFT_DIR, RIGHT_DIR, compile_tm_to_universal_tape


def _run_instance(instance: TMInstance, *, fuel: int = 500_000):
    encoded = Compiler().compile(instance)
    band_artifact = encoded.to_band_artifact()
    program_artifact = UniversalInterpreter.for_encoded(encoded).lower_for_band(band_artifact)
    result = program_artifact.run(band_artifact, fuel=fuel)
    final_band = type(encoded.to_encoded_band()).from_runtime_tape(encoded.encoding, result["tape"])
    return result, decoded_view_from_encoded_band(final_band)


def test_tm_program_wraps_source_transitions_immutably() -> None:
    transitions = {("q0", "1"): ("qH", "0", 1)}
    program = TMProgram(transitions, initial_state="q0", halt_state="qH", blank="_")
    transitions[("q0", "1")] = ("q0", "1", 1)

    assert len(program) == 1
    assert program[("q0", "1")] == ("qH", "0", 1)
    assert program.transition_for("q0", "1") == ("qH", "0", 1)
    assert program.states() == ("q0", "qH")
    assert program.symbols() == ("0", "1", "_")
    assert program.required_abi(source_symbols=("1",)) == TMAbi(1, 2, 1, "mtm-v1", "min[Wq=1,Ws=2,Wd=1]")


def test_tm_program_rejects_unsupported_direction() -> None:
    try:
        TMProgram({("q0", "1"): ("qH", "0", 0)}, initial_state="q0", halt_state="qH")
    except ValueError as exc:
        assert "unsupported move direction" in str(exc)
    else:
        raise AssertionError("expected unsupported direction to be rejected")


def test_abi_literal_round_trip() -> None:
    abi = TMAbi(3, 4, 2, "mtm-v2", "custom-family")

    literal = abi_to_literal(abi)
    loaded = abi_from_literal(literal)

    assert literal == {
        "state_width": 3,
        "symbol_width": 4,
        "dir_width": 2,
        "grammar_version": "mtm-v2",
        "family_label": "custom-family",
    }
    assert loaded == abi


def test_abi_compatibility_ignores_family_label_and_rejects_shape_mismatches() -> None:
    left = TMAbi(3, 4, 2, "mtm-v1", "left")
    right = TMAbi(3, 4, 2, "mtm-v1", "right")
    wrong_symbol_width = TMAbi(3, 5, 2, "mtm-v1", "left")
    wrong_grammar = TMAbi(3, 4, 2, "mtm-v2", "left")

    assert abi_compatible(left, right) is True
    assert_abi_compatible(left, right)
    assert abi_compatible(left, wrong_symbol_width) is False
    assert abi_compatible(left, wrong_grammar) is False

    for incompatible in (wrong_symbol_width, wrong_grammar):
        try:
            assert_abi_compatible(left, incompatible)
        except ValueError as exc:
            assert "ABI mismatch" in str(exc)
        else:
            raise AssertionError("expected incompatible ABI to be rejected")


def test_semantic_view_from_encoded_band() -> None:
    band = load_fixture("incrementer").build_band()
    view = decoded_view_from_encoded_band(band)

    assert band.minimal_abi == TMAbi(2, 2, 1, "mtm-v1", "min[Wq=2,Ws=2,Wd=1]")
    assert band.target_abi == TMAbi(2, 2, 1, "mtm-v1", "U[Wq=2,Ws=2,Wd=1]")
    assert view.current_state == "qFindMargin"
    assert view.registers.cur_state == "qFindMargin"
    assert view.registers.cur_symbol == "_"
    assert view.registers.halt_state == "qDone"
    assert view.registers.blank_symbol == "_"
    assert view.registers.left_dir == L
    assert view.registers.right_dir == R
    assert len(view.rules) == 6
    assert view.simulated_tape.cells[:4] == ("1", "0", "1", "1")
    assert view.simulated_head == 0
    assert view.simulated_tape.head == 0


def test_encoded_register_band_carries_guest_owned_constants() -> None:
    fixture = load_fixture("incrementer")
    band = fixture.build_band()
    view = decoded_view_from_encoded_band(band)

    assert HALT_STATE in band.left_band
    assert BLANK_SYMBOL in band.left_band
    assert LEFT_DIR in band.left_band
    assert RIGHT_DIR in band.left_band
    assert view.registers.halt_state == fixture.halt_state
    assert view.registers.blank_symbol == fixture.band.blank
    assert view.registers.left_dir == L
    assert view.registers.right_dir == R


def test_trivial_halted_blank_input_preserves_blank_cell() -> None:
    blank = "_"
    band = TMBand.from_dict({}, head=0, blank=blank)
    program = TMProgram({}, initial_state="HALT", halt_state="HALT", blank=blank)

    result, view = _run_instance(TMInstance(program, band, "HALT", "HALT"))

    assert result["status"] == "halted"
    assert view.current_state == "HALT"
    assert view.simulated_tape.left_band == ()
    assert view.simulated_tape.right_band == ("_",)
    assert view.simulated_tape.head == 0


def test_one_step_right_constructs_blank_right_cell_end_to_end() -> None:
    blank = "_"
    band = TMBand.from_dict({}, head=0, blank=blank)
    program = TMProgram({
        ("q0", blank): ("q1", blank, R),
        ("q1", blank): ("HALT", blank, R),
    }, initial_state="q0", halt_state="HALT", blank=blank)

    result, view = _run_instance(TMInstance(program, band, "q0", "HALT"), fuel=5_000)

    assert result["status"] == "halted"
    assert view.current_state == "HALT"
    assert view.simulated_tape.left_band == ()
    assert view.simulated_tape.right_band == ("_", "_", "_")
    assert view.simulated_tape.head == 2


def test_halt_transition_moves_after_writing_on_left_tape() -> None:
    blank = "_"
    band = TMBand.from_dict({}, head=0, blank=blank)
    program = TMProgram({
        ("q0", blank): ("q1", "A", L),
        ("q1", blank): ("HALT", "C", L),
    }, initial_state="q0", halt_state="HALT", blank=blank)

    result, view = _run_instance(TMInstance(program, band, "q0", "HALT"), fuel=20_000)

    assert result["status"] == "halted"
    assert view.current_state == "HALT"
    assert view.simulated_tape.left_band == (blank, "C")
    assert view.simulated_tape.right_band == ("A",)
    assert view.simulated_tape.head == -2


def test_utm_encoded_and_artifact_helpers() -> None:
    band = load_fixture("incrementer").build_band()
    minimal_abi = TMAbi(2, 2, 1, "mtm-v1", "incrementer-min")
    encoded = utm_encoded_from_band(band, minimal_abi=minimal_abi)
    artifact = utm_artifact_from_band(band, minimal_abi=minimal_abi)
    round_tripped_band = encoded_band_from_utm_artifact(artifact)

    assert encoded.current_state == "qFindMargin"
    assert encoded.simulated_head == 0
    assert encoded.target_abi == TMAbi(2, 2, 1, "mtm-v1", "U[Wq=2,Ws=2,Wd=1]")
    assert encoded.minimal_abi == minimal_abi
    assert artifact.target_abi == encoded.target_abi
    assert artifact.minimal_abi == minimal_abi
    assert artifact.left_band[0] == "#END_TAPE_LEFT"
    assert "#REGS" in artifact.left_band
    assert artifact.right_band[0] == "#TAPE"
    assert artifact.start_head < 0
    assert round_tripped_band.left_band == band.left_band
    assert round_tripped_band.right_band == band.right_band
    assert round_tripped_band.minimal_abi == minimal_abi
    assert round_tripped_band.target_abi == artifact.target_abi
    assert isinstance(artifact, UTMBandArtifact)


def test_utm_encoded_emission_methods() -> None:
    band = load_fixture("incrementer").build_band()
    encoded = utm_encoded_from_band(band)

    artifact = encoded.to_band_artifact()
    view = encoded.decoded_view()

    assert artifact == utm_artifact_from_band(band)
    assert artifact.to_encoded_band() == band
    assert view == decoded_view_from_encoded_band(band)


def test_utm_artifact_round_trip(tmp_path) -> None:
    band = load_fixture("incrementer").build_band()
    artifact = utm_artifact_from_band(band)
    path = tmp_path / "incrementer.utm.band"

    write_utm_artifact(path, artifact)

    loaded = read_utm_artifact(path)

    assert loaded == artifact
    assert loaded.to_encoded_band() == band
    assert loaded.to_runtime_tape() == band.runtime_tape


def test_primary_artifact_class_methods_round_trip(tmp_path) -> None:
    band = load_fixture("incrementer").build_band()
    artifact = utm_artifact_from_band(band)
    path = tmp_path / "incrementer.utm.band"

    artifact.write(path)
    loaded = UTMBandArtifact.read(path)

    assert loaded == artifact
    assert loaded.to_encoded_band() == band
    assert loaded.to_runtime_tape() == band.runtime_tape


def test_source_artifact_round_trip(tmp_path) -> None:
    fixture = load_fixture("incrementer")
    source = SourceArtifact(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
        name=fixture.name,
        note=fixture.note,
    )
    path = tmp_path / "incrementer.mtm.source"

    source.write(path)
    loaded = SourceArtifact.read(path)

    assert loaded == source
    assert loaded.to_instance() == TMInstance(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )


def test_primary_tm_program_names_and_io(tmp_path) -> None:
    builder = TMBuilder(["0"])
    builder.emit("start", "0", builder.halt_state, "0", 0)
    raw_tm = builder.build("start")
    path = tmp_path / "utm.tm"

    assert isinstance(raw_tm, TMTransitionProgram)
    raw_tm.write(path)
    loaded = TMTransitionProgram.read(path)
    instance = RawTMInstance(program=loaded, tape={0: "_RUNTIME_BLANK"}, head=0, state=loaded.start_state)

    assert loaded == raw_tm
    assert loaded.transitions == raw_tm.prog
    try:
        loaded.transitions[("start", "0")] = ("other", "0", 0)
    except TypeError:
        pass
    else:
        raise AssertionError("expected transitions alias to be read-only")
    assert instance.program == raw_tm
    assert instance.state == raw_tm.start_state


def test_utm_program_artifact_reads_old_raw_tm_without_abi_metadata(tmp_path) -> None:
    builder = TMBuilder(["0"])
    builder.emit("start", "0", builder.halt_state, "0", 0)
    raw_tm = builder.build("start")
    path = tmp_path / "old.tm"

    raw_tm.write(path)
    loaded = UTMProgramArtifact.read(path)

    assert loaded.program == raw_tm
    assert loaded.target_abi is None
    assert loaded.minimal_abi is None
    assert "target_abi" not in path.read_text()
    assert "minimal_abi" not in path.read_text()


def test_raw_guest_encoding_infers_states_symbols_and_stay_direction() -> None:
    builder = TMBuilder(["0", "X"], halt_state="halt")
    builder.emit("start", "0", "stay", "X", S)
    builder.emit("stay", "X", "halt", "X", 1)
    program = builder.build("start")
    instance = RawTMInstance(program=program, tape={0: "0", 3: "Y"}, head=0, state="current")

    minimal = infer_raw_guest_minimal_abi(instance)
    encoding = build_raw_guest_encoding(instance)

    assert minimal == TMAbi(2, 2, 2, "mtm-v1", "raw-min[Wq=2,Ws=2,Wd=2]")
    assert encoding.state_ids.keys() >= {"current", "start", "stay", "halt"}
    assert encoding.symbol_ids.keys() >= {program.blank, "0", "X", "Y"}
    assert encoding.direction_ids == {-1: 0, 1: 1, 0: 2}
    assert encoding.direction_width == 2
    assert encoding.initial_state == "current"


def test_raw_guest_encoding_rejects_unsupported_raw_move() -> None:
    builder = TMBuilder(["0"], halt_state="halt")
    builder.emit("start", "0", "halt", "0", 2)
    instance = RawTMInstance(program=builder.build("start"), tape={0: "0"}, head=0, state="start")

    try:
        build_raw_guest_encoding(instance)
    except ValueError as exc:
        assert "unsupported raw move direction" in str(exc)
    else:
        raise AssertionError("expected unsupported raw move to be rejected")


def test_universal_dispatch_treats_non_left_non_right_direction_as_stay() -> None:
    builder = TMBuilder(["0"], halt_state="halt")
    builder.emit("start", "0", "halt", "0", S)
    instance = RawTMInstance(program=builder.build("start"), tape={0: "0"}, head=0, state="start")
    encoding = build_raw_guest_encoding(instance)
    program = build_universal_meta_asm(encoding)

    start_step = next(block for block in program.blocks if block.label == "START_STEP")
    dispatch_move = next(block for block in program.blocks if block.label == "DISPATCH_MOVE")
    check_right = next(block for block in program.blocks if block.label == "CHECK_RIGHT")

    assert encoding.direction_ids == {-1: 0, 1: 1, 0: 2}
    assert start_step.instructions[0] == CompareGlobalGlobal("#CUR_STATE", "#HALT_STATE", encoding.state_width)
    assert dispatch_move.instructions[0] == CompareGlobalGlobal("#MOVE_DIR", "#LEFT_DIR", encoding.direction_width)
    assert check_right.instructions[0] == CompareGlobalGlobal("#MOVE_DIR", "#RIGHT_DIR", encoding.direction_width)
    assert check_right.instructions[-1].label_equal == "MOVE_RIGHT"
    assert check_right.instructions[-1].label_not_equal == "START_STEP"


def test_compile_raw_guest_preserves_sparse_tape_and_head_blank() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt")
    builder.emit("start", "0", "halt", "1", S)
    program = builder.build("start")
    instance = RawTMInstance(
        program=program,
        tape={-2: "1", 0: "0"},
        head=2,
        state="start",
    )

    encoded = compile_raw_guest(instance)
    artifact = encoded.to_band_artifact()
    view = encoded.decoded_view()

    assert view.current_state == "start"
    assert view.registers.halt_state == "halt"
    assert view.registers.blank_symbol == program.blank
    assert view.registers.left_dir == -1
    assert view.registers.right_dir == 1
    assert view.simulated_tape.left_band == ("1", program.blank)
    assert view.simulated_tape.right_band == ("0", program.blank, program.blank)
    assert view.simulated_tape.head == 2
    assert artifact.target_abi == encoded.target_abi
    assert artifact.minimal_abi == encoded.minimal_abi


def test_compiled_raw_guest_band_runs_on_lowered_host() -> None:
    builder = TMBuilder(["0", "1"], halt_state="halt")
    builder.emit("start", "0", "halt", "1", S)
    instance = RawTMInstance(
        program=builder.build("start"),
        tape={0: "0"},
        head=0,
        state="start",
    )

    encoded = compile_raw_guest(instance)
    band_artifact = encoded.to_band_artifact()
    program_artifact = UniversalInterpreter.for_encoded(encoded).lower_for_band(band_artifact)
    result = program_artifact.run(band_artifact, fuel=50_000)
    final_band = type(encoded.to_encoded_band()).from_runtime_tape(encoded.encoding, result["tape"])
    final_view = decoded_view_from_encoded_band(final_band)

    assert result["status"] == "halted"
    assert final_view.current_state == "halt"
    assert final_view.simulated_tape.right_band[0] == "1"


def test_utm_program_artifact_round_trip_and_run(tmp_path) -> None:
    band = load_fixture("incrementer").build_band()
    band_artifact = utm_artifact_from_band(band)
    interpreter = UniversalInterpreter.for_encoding(band.encoding)
    program_artifact = interpreter.lower_for_band(band_artifact)
    path = tmp_path / "utm.tm"

    program_artifact.write(path)
    loaded = UTMProgramArtifact.read(path)
    raw_loaded = TMTransitionProgram.read(path)
    instance = band_artifact.to_raw_instance(loaded)
    legacy_instance = band_artifact.to_run_config(loaded)
    result = loaded.run(band_artifact, fuel=200_000)
    final_band = type(band).from_runtime_tape(band.encoding, result["tape"])
    final_view = decoded_view_from_encoded_band(final_band)

    assert loaded.program == program_artifact.program
    assert raw_loaded == program_artifact.program
    assert loaded.target_abi == band_artifact.target_abi
    assert loaded.minimal_abi == band_artifact.minimal_abi
    assert "target_abi" in path.read_text()
    assert "minimal_abi" in path.read_text()
    assert legacy_instance == instance
    assert instance.head == band_artifact.start_head
    assert instance.state == loaded.program.start_state
    assert result["status"] == "halted"
    assert result["state"] == "U_HALT"
    assert final_view.current_state == band.encoding.halt_state
    assert final_view.simulated_tape.cells[:8] == ("1", "1", "0", "0", "_", "_", "_", "_")


def test_utm_program_artifact_run_allows_missing_program_abi_metadata() -> None:
    band = load_fixture("incrementer").build_band()
    band_artifact = utm_artifact_from_band(band)
    program = UniversalInterpreter.for_encoding(band.encoding).lower_for_band(band_artifact).program
    program_artifact = UTMProgramArtifact(program=program)

    result = program_artifact.run(band_artifact, fuel=200_000)

    assert result["status"] == "halted"


def test_utm_program_artifact_run_rejects_incompatible_abi_metadata() -> None:
    band = load_fixture("incrementer").build_band()
    band_artifact = utm_artifact_from_band(band)
    program = UniversalInterpreter.for_encoding(band.encoding).lower_for_band(band_artifact).program
    mismatches = (
        ("state_width", TMAbi(
            band_artifact.target_abi.state_width + 1,
            band_artifact.target_abi.symbol_width,
            band_artifact.target_abi.dir_width,
            band_artifact.target_abi.grammar_version,
            "wrong-state",
        )),
        ("symbol_width", TMAbi(
            band_artifact.target_abi.state_width,
            band_artifact.target_abi.symbol_width + 1,
            band_artifact.target_abi.dir_width,
            band_artifact.target_abi.grammar_version,
            "wrong-symbol",
        )),
        ("dir_width", TMAbi(
            band_artifact.target_abi.state_width,
            band_artifact.target_abi.symbol_width,
            band_artifact.target_abi.dir_width + 1,
            band_artifact.target_abi.grammar_version,
            "wrong-dir",
        )),
        ("grammar_version", TMAbi(
            band_artifact.target_abi.state_width,
            band_artifact.target_abi.symbol_width,
            band_artifact.target_abi.dir_width,
            "mtm-v2",
            "wrong-grammar",
        )),
    )

    for field, wrong_abi in mismatches:
        program_artifact = UTMProgramArtifact(program=program, target_abi=wrong_abi)
        try:
            program_artifact.run(band_artifact)
        except ValueError as exc:
            assert "ABI mismatch" in str(exc)
            assert field in str(exc)
        else:
            raise AssertionError(f"expected {field} mismatch to be rejected")


def test_universal_interpreter_for_encoded_matches_direct_lowering() -> None:
    band = load_fixture("incrementer").build_band()
    encoded = utm_encoded_from_band(band)
    interpreter = UniversalInterpreter.for_encoded(encoded)
    band_artifact = encoded.to_band_artifact()

    artifact = interpreter.lower_for_band(band_artifact)
    direct_program = build_universal_meta_asm(band.encoding)
    direct_lowered = lower_program_to_raw_tm(
        direct_program,
        interpreter.alphabet_for_band(band_artifact),
    )

    assert interpreter.to_meta_asm() == direct_program
    assert artifact.program == direct_lowered


def test_source_band_helper() -> None:
    band = TMBand(right_band=("1", "0", "1", "1"), head=0, blank="_")
    assert band == TMBand(right_band=("1", "0", "1", "1"), head=0, blank="_")


def test_source_band_from_dict_splits_negative_and_nonnegative_sides() -> None:
    band = TMBand.from_dict({-2: "1", 0: "0", 2: "1"}, head=-2, blank="_")

    assert band.left_band == ("1", "_")
    assert band.right_band == ("0", "_", "1")
    assert band.cells == ("1", "_", "0", "_", "1")
    assert band.head == -2


def test_blank_symbol_encodes_as_zero_bits() -> None:
    band = load_fixture("palindrome").build_band()

    assert band.encoding.symbol_ids[band.encoding.blank] == 0


def test_encoded_band_preserves_negative_source_head() -> None:
    fixture = load_fixture("incrementer")
    source_band = TMBand.from_dict({-1: "1", 0: "0"}, head=-1, blank="_")
    band = compile_tm_to_universal_tape(
        fixture.tm_program,
        source_band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    view = decoded_view_from_encoded_band(band)

    assert view.simulated_tape.left_band == ("1",)
    assert view.simulated_tape.right_band == ("0",)
    assert view.simulated_tape.head == -1


def test_minimal_abi_inference_and_explicit_target_abi() -> None:
    fixture = load_fixture("incrementer")
    inferred = infer_minimal_abi(
        fixture.tm_program,
        fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    target = TMAbi(3, 4, 2, "mtm-v1", "U[Wq=3,Ws=4,Wd=2]")
    band = compile_tm_to_universal_tape(
        fixture.tm_program,
        fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
        abi=target,
    )

    assert inferred == TMAbi(2, 2, 1, "mtm-v1", "min[Wq=2,Ws=2,Wd=1]")
    assert band.minimal_abi == inferred
    assert band.target_abi == target
    assert band.encoding.state_width == 3
    assert band.encoding.symbol_width == 4
    assert band.encoding.direction_width == 2


def test_compiler_infers_abi_and_compiles_to_utm_encoded() -> None:
    fixture = load_fixture("incrementer")
    instance = TMInstance(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    compiler = Compiler()

    inferred = compiler.infer_abi(instance)
    encoded = compiler.compile(instance)

    assert inferred == TMAbi(2, 2, 1, "mtm-v1", "min[Wq=2,Ws=2,Wd=1]")
    assert encoded == utm_encoded_from_band(fixture.build_band())
    assert encoded.to_band_artifact() == utm_artifact_from_band(fixture.build_band())


def test_compiler_resolves_endpoints_from_tm_program() -> None:
    band = TMBand.from_dict({}, head=0, blank="_")
    program = TMProgram({}, initial_state="program_start", halt_state="program_halt", blank="_")

    encoded = Compiler().compile(TMInstance(program, band))

    assert encoded.current_state == "program_start"
    assert encoded.encoding.initial_state == "program_start"
    assert encoded.encoding.halt_state == "program_halt"


def test_compiler_instance_endpoints_override_program_endpoints() -> None:
    band = TMBand.from_dict({}, head=0, blank="_")
    program = TMProgram({}, initial_state="program_start", halt_state="program_halt", blank="_")

    encoded = Compiler().compile(
        TMInstance(
            program,
            band,
            initial_state="instance_start",
            halt_state="instance_halt",
        )
    )

    assert encoded.current_state == "instance_start"
    assert encoded.encoding.initial_state == "instance_start"
    assert encoded.encoding.halt_state == "instance_halt"


def test_compiler_resolves_endpoints_from_compiler_defaults() -> None:
    band = TMBand.from_dict({}, head=0, blank="_")
    program = TMProgram({}, blank="_")

    encoded = Compiler(initial_state="compiler_start", halt_state="compiler_halt").compile(TMInstance(program, band))

    assert encoded.current_state == "compiler_start"
    assert encoded.encoding.initial_state == "compiler_start"
    assert encoded.encoding.halt_state == "compiler_halt"


def test_compiler_rejects_source_blank_mismatch() -> None:
    band = TMBand.from_dict({}, head=0, blank="_")
    program = TMProgram({}, initial_state="start", halt_state="halt", blank=" ")

    try:
        Compiler().compile(TMInstance(program, band))
    except ValueError as exc:
        assert "source blank mismatch" in str(exc)
    else:
        raise AssertionError("expected blank mismatch to be rejected")


def test_compiler_uses_selected_target_abi() -> None:
    fixture = load_fixture("incrementer")
    target = TMAbi(3, 4, 2, "mtm-v1", "U[Wq=3,Ws=4,Wd=2]")
    instance = TMInstance(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )

    encoded = Compiler(target_abi=target).compile(instance)

    assert encoded.target_abi == target
    assert encoded.to_band_artifact().target_abi == target


def test_wider_abi_incrementer_runs_end_to_end() -> None:
    fixture = load_fixture("incrementer")
    target = TMAbi(3, 4, 2, "mtm-v1", "U[Wq=3,Ws=4,Wd=2]")
    instance = TMInstance(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )

    encoded = Compiler(target_abi=target).compile(instance)
    band_artifact = encoded.to_band_artifact()
    program_artifact = UniversalInterpreter.for_encoded(encoded).lower_for_band(band_artifact)
    result = program_artifact.run(band_artifact, fuel=200_000)
    final_band = type(encoded.to_encoded_band()).from_runtime_tape(encoded.encoding, result["tape"])
    final_view = decoded_view_from_encoded_band(final_band)

    assert encoded.minimal_abi == TMAbi(2, 2, 1, "mtm-v1", "min[Wq=2,Ws=2,Wd=1]")
    assert encoded.target_abi == target
    assert result["status"] == "halted"
    assert result["state"] == "U_HALT"
    assert final_view.current_state == fixture.halt_state
    assert final_view.simulated_tape.cells[:8] == ("1", "1", "0", "0", "_", "_", "_", "_")


def test_palindrome_compiles_with_wider_target_abis() -> None:
    fixture = load_fixture("palindrome")
    expected_minimal = TMAbi(3, 2, 1, "mtm-v1", "min[Wq=3,Ws=2,Wd=1]")
    targets = (
        TMAbi(4, 3, 2, "mtm-v1", "U[Wq=4,Ws=3,Wd=2]"),
        TMAbi(5, 5, 3, "mtm-v1", "U[Wq=5,Ws=5,Wd=3]"),
    )
    instance = TMInstance(
        program=fixture.tm_program,
        band=fixture.band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )

    for target in targets:
        encoded = Compiler(target_abi=target).compile(instance)
        band_artifact = encoded.to_band_artifact()
        program_artifact = UniversalInterpreter.for_encoded(encoded).lower_for_band(band_artifact)
        decoded = encoded.decoded_view()

        assert encoded.minimal_abi == expected_minimal
        assert encoded.target_abi == target
        assert band_artifact.target_abi == target
        assert program_artifact.target_abi == target
        assert program_artifact.minimal_abi == expected_minimal
        assert encoded.encoding.state_width == target.state_width
        assert encoded.encoding.symbol_width == target.symbol_width
        assert encoded.encoding.direction_width == target.dir_width
        assert encoded.encoding.symbol_ids[fixture.band.blank] == 0
        assert decoded.simulated_tape.left_band == ("1",)
        assert decoded.simulated_tape.right_band == ("0", "1")
        assert decoded.simulated_tape.head == -1
        assert len(program_artifact.program.prog) > 0


def test_compile_rejects_too_small_abi() -> None:
    fixture = load_fixture("incrementer")
    too_small = TMAbi(1, 1, 1, "mtm-v1", "too-small")

    try:
        fixture.build_band(abi=too_small)
    except ValueError as exc:
        assert "selected ABI too small" in str(exc)
        assert "states require" in str(exc)
    else:
        raise AssertionError("expected selected ABI to be rejected")


def test_compile_rejects_grammar_version_mismatch() -> None:
    fixture = load_fixture("incrementer")
    wrong_grammar = TMAbi(3, 4, 2, "mtm-v2", "wrong-grammar")

    try:
        fixture.build_band(abi=wrong_grammar)
    except ValueError as exc:
        assert "selected ABI incompatible" in str(exc)
        assert "grammar_version" in str(exc)
    else:
        raise AssertionError("expected grammar-version mismatch to be rejected")


def test_runtime_tape_printer() -> None:
    band = load_fixture("incrementer").build_band()

    assert "RUNTIME TAPE" in pretty_runtime_tape(band.runtime_tape)


def test_public_boundary_is_small() -> None:
    public = set(mtm.__all__)

    expected = {
        "L",
        "R",
        "SourceArtifact",
        "TMProgram",
        "TMBand",
        "TMInstance",
        "TMAbi",
        "Encoding",
        "Compiler",
        "UTMEncoded",
        "UTMBandArtifact",
        "UTMProgramArtifact",
        "TMTransitionProgram",
        "RawTMInstance",
        "DecodedBandView",
        "UniversalInterpreter",
        "TMFixture",
        "list_fixtures",
        "load_fixture",
        "load_python_tm",
        "load_python_tm_instance",
    }

    assert expected == public
    assert "lower_instruction" not in public
    assert "TMBuilder" not in public
