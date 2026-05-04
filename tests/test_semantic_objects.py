import mtm
from mtm import (
    build_encoded_band,
    build_outer_tape,
    build_runtime_tape,
    Compiler,
    compile_tm_to_encoded_band,
    compile_tm_to_universal_tape,
    compile_tm_to_runtime_tape,
    build_universal_meta_asm,
    infer_minimal_abi,
    lower_program_to_raw_tm,
    TMAbi,
    TMBand,
    TMInstance,
    TMProgram,
    decoded_view_from_encoded_band,
    encoded_band_from_utm_artifact,
    load_fixture,
    materialize_raw_tape,
    materialize_runtime_tape,
    pretty_outer_tape,
    pretty_runtime_tape,
    read_utm,
    read_utm_artifact,
    source_band_from_simulated_tape,
    split_outer_tape,
    split_raw_tape,
    split_runtime_tape,
    utm_artifact_from_band,
    utm_encoded_from_band,
    UniversalInterpreter,
    write_utm_artifact,
)
from mtm.raw_transition_tm import TMBuilder, TMTransitionProgram
from mtm.semantic_objects import TMRunConfig, UTMBandArtifact, UTMProgramArtifact


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


def test_semantic_view_from_encoded_band() -> None:
    band = load_fixture("incrementer").build_band()
    view = decoded_view_from_encoded_band(band)

    assert band.minimal_abi == TMAbi(2, 2, 1, "mtm-v1", "min[Wq=2,Ws=2,Wd=1]")
    assert band.target_abi == TMAbi(2, 2, 1, "mtm-v1", "U[Wq=2,Ws=2,Wd=1]")
    assert view.current_state == "qFindMargin"
    assert view.registers.cur_state == "qFindMargin"
    assert view.registers.cur_symbol == "_"
    assert len(view.rules) == 6
    assert view.simulated_tape.cells[:4] == ("1", "0", "1", "1")
    assert view.simulated_head == 0
    assert view.simulated_tape.head == 0


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
    assert artifact.left_band[0] == "#REGS"
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
    legacy_band, start_head = read_utm(path)

    assert loaded == artifact
    assert loaded.to_encoded_band() == band
    assert loaded.to_runtime_tape() == band.runtime_tape
    assert legacy_band == band
    assert start_head == artifact.start_head


def test_primary_artifact_class_methods_round_trip(tmp_path) -> None:
    band = load_fixture("incrementer").build_band()
    artifact = utm_artifact_from_band(band)
    path = tmp_path / "incrementer.utm.band"

    artifact.write(path)
    loaded = UTMBandArtifact.read(path)

    assert loaded == artifact
    assert loaded.to_encoded_band() == band
    assert loaded.to_runtime_tape() == band.runtime_tape


def test_primary_tm_program_names_and_io(tmp_path) -> None:
    builder = TMBuilder(["0"])
    builder.emit("start", "0", builder.halt_state, "0", 0)
    raw_tm = builder.build("start")
    path = tmp_path / "utm.tm"

    assert isinstance(raw_tm, TMTransitionProgram)
    raw_tm.write(path)
    loaded = TMTransitionProgram.read(path)
    config = TMRunConfig(program=loaded, tape={0: "_OUTER_BLANK"}, head=0, state=loaded.start_state)

    assert loaded == raw_tm
    assert config.program == raw_tm
    assert config.state == raw_tm.start_state


def test_utm_program_artifact_round_trip_and_run(tmp_path) -> None:
    band = load_fixture("incrementer").build_band()
    band_artifact = utm_artifact_from_band(band)
    interpreter = UniversalInterpreter.for_encoding(band.encoding)
    program_artifact = interpreter.lower_for_band(band_artifact)
    path = tmp_path / "utm.tm"

    program_artifact.write(path)
    loaded = UTMProgramArtifact.read(
        path,
        target_abi=band_artifact.target_abi,
        minimal_abi=band_artifact.minimal_abi,
    )
    config = band_artifact.to_run_config(loaded)
    result = loaded.run(band_artifact, fuel=200_000)
    final_band = type(band).from_runtime_tape(band.encoding, result["tape"])
    final_view = decoded_view_from_encoded_band(final_band)

    assert loaded.program == program_artifact.program
    assert loaded.target_abi == band_artifact.target_abi
    assert config.head == band_artifact.start_head
    assert config.state == loaded.program.start_state
    assert result["status"] == "halted"
    assert result["state"] == "U_HALT"
    assert final_view.current_state == band.encoding.halt_state
    assert final_view.simulated_tape.cells[:8] == ("1", "1", "0", "0", "_", "_", "_", "_")


def test_universal_interpreter_for_encoded_matches_legacy_lowering() -> None:
    band = load_fixture("incrementer").build_band()
    encoded = utm_encoded_from_band(band)
    interpreter = UniversalInterpreter.for_encoded(encoded)
    band_artifact = encoded.to_band_artifact()

    artifact = interpreter.lower_for_band(band_artifact)
    legacy_program = build_universal_meta_asm(band.encoding)
    legacy_lowered = lower_program_to_raw_tm(
        legacy_program,
        interpreter.alphabet_for_band(band_artifact),
    )

    assert interpreter.to_meta_asm() == legacy_program
    assert artifact.program == legacy_lowered


def test_source_band_helper() -> None:
    band = source_band_from_simulated_tape(("1", "0", "1", "1"), 0, blank="_")
    assert band == TMBand(cells=("1", "0", "1", "1"), head=0, blank="_")


def test_minimal_abi_inference_and_explicit_target_abi() -> None:
    fixture = load_fixture("incrementer")
    source_band = source_band_from_simulated_tape(
        tuple([fixture.blank] * fixture.blanks_left + fixture.input_symbols + [fixture.blank] * fixture.blanks_right),
        fixture.blanks_left,
        blank=fixture.blank,
    )
    inferred = infer_minimal_abi(
        fixture.tm_program,
        source_band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    target = TMAbi(3, 4, 2, "mtm-v1", "U[Wq=3,Ws=4,Wd=2]")
    band = compile_tm_to_universal_tape(
        fixture.tm_program,
        source_band,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
        blank=fixture.blank,
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
        band=TMBand(
            cells=tuple([fixture.blank] * fixture.blanks_left + fixture.input_symbols + [fixture.blank] * fixture.blanks_right),
            head=fixture.blanks_left,
            blank=fixture.blank,
        ),
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )
    compiler = Compiler()

    inferred = compiler.infer_abi(instance)
    encoded = compiler.compile(instance)

    assert inferred == TMAbi(2, 2, 1, "mtm-v1", "min[Wq=2,Ws=2,Wd=1]")
    assert encoded == utm_encoded_from_band(fixture.build_band())
    assert encoded.to_band_artifact() == utm_artifact_from_band(fixture.build_band())


def test_compiler_uses_selected_target_abi() -> None:
    fixture = load_fixture("incrementer")
    target = TMAbi(3, 4, 2, "mtm-v1", "U[Wq=3,Ws=4,Wd=2]")
    instance = TMInstance(
        program=fixture.tm_program,
        band=TMBand(
            cells=tuple([fixture.blank] * fixture.blanks_left + fixture.input_symbols + [fixture.blank] * fixture.blanks_right),
            head=fixture.blanks_left,
            blank=fixture.blank,
        ),
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
    )

    encoded = Compiler(target_abi=target).compile(instance)

    assert encoded.target_abi == target
    assert encoded.to_band_artifact().target_abi == target


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


def test_runtime_alias_exports_remain_compatible() -> None:
    band = load_fixture("incrementer").build_band()
    fixture = load_fixture("incrementer")

    assert build_runtime_tape is build_outer_tape
    assert compile_tm_to_runtime_tape is compile_tm_to_universal_tape
    assert compile_tm_to_runtime_tape is compile_tm_to_encoded_band
    assert materialize_raw_tape is materialize_runtime_tape
    assert split_raw_tape is split_runtime_tape
    assert split_outer_tape is split_runtime_tape
    assert pretty_runtime_tape is pretty_outer_tape
    assert build_encoded_band(
        fixture.tm_program,
        fixture.input_symbols,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
        blank=fixture.blank,
        blanks_left=fixture.blanks_left,
        blanks_right=fixture.blanks_right,
    ) == build_outer_tape(
        fixture.tm_program,
        fixture.input_symbols,
        initial_state=fixture.initial_state,
        halt_state=fixture.halt_state,
        blank=fixture.blank,
        blanks_left=fixture.blanks_left,
        blanks_right=fixture.blanks_right,
    )
    assert "RUNTIME TAPE" in pretty_runtime_tape(band.runtime_tape)


def test_public_compatibility_boundary_is_explicit() -> None:
    band = load_fixture("incrementer").build_band()
    public = set(mtm.__all__)

    primary_names = {
        "L",
        "R",
        "TMProgram",
        "TMBand",
        "TMInstance",
        "TMAbi",
        "Encoding",
        "Compiler",
        "UTMEncoded",
        "UTMBandArtifact",
        "MetaASMProgram",
        "UTMProgramArtifact",
        "TMTransitionProgram",
        "TMRunConfig",
        "DecodedBandView",
        "UniversalInterpreter",
    }
    alias_names = {
        "build_encoded_band",
        "build_runtime_tape",
        "build_outer_tape",
        "compile_tm_to_universal_tape",
        "compile_tm_to_runtime_tape",
        "compile_tm_to_encoded_band",
        "materialize_runtime_tape",
        "materialize_raw_tape",
        "split_runtime_tape",
        "split_raw_tape",
        "split_outer_tape",
        "pretty_runtime_tape",
        "pretty_outer_tape",
        "run_meta_asm_runtime",
        "run_meta_asm_block_runtime",
        "run_meta_asm_host",
        "run_meta_asm_block",
        "build_utm_encoded",
        "build_utm_encoding_artifact",
        "utm_encoded_from_band",
        "utm_artifact_from_band",
        "decoded_view_from_encoded_band",
        "encoded_band_from_utm_artifact",
    }

    assert primary_names <= public
    assert alias_names <= public
    assert "lower_instruction" not in public
    assert "TMBuilder" not in public
    assert mtm.build_utm_encoded(band) == mtm.utm_encoded_from_band(band)
    assert mtm.build_utm_encoding_artifact(band) == mtm.utm_artifact_from_band(band)
