from mtm import (
    build_outer_tape,
    build_runtime_tape,
    compile_tm_to_encoded_band,
    compile_tm_to_runtime_tape,
    TMAbi,
    TMBand,
    decoded_view_from_encoded_band,
    encoded_band_from_utm_artifact,
    load_fixture,
    pretty_outer_tape,
    pretty_runtime_tape,
    read_utm,
    read_utm_artifact,
    source_band_from_simulated_tape,
    utm_artifact_from_band,
    utm_encoded_from_band,
    write_utm_artifact,
)


def test_semantic_view_from_encoded_band() -> None:
    band = load_fixture("incrementer").build_band()
    view = decoded_view_from_encoded_band(band)

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


def test_utm_artifact_round_trip(tmp_path) -> None:
    band = load_fixture("incrementer").build_band()
    artifact = utm_artifact_from_band(band)
    path = tmp_path / "incrementer.utm"

    write_utm_artifact(path, artifact)

    loaded = read_utm_artifact(path)
    legacy_band, start_head = read_utm(path)

    assert loaded == artifact
    assert loaded.to_encoded_band() == band
    assert legacy_band == band
    assert start_head == artifact.start_head


def test_source_band_helper() -> None:
    band = source_band_from_simulated_tape(("1", "0", "1", "1"), 0, blank="_")
    assert band == TMBand(cells=("1", "0", "1", "1"), head=0, blank="_")


def test_runtime_alias_exports_remain_compatible() -> None:
    band = load_fixture("incrementer").build_band()

    assert build_runtime_tape is build_outer_tape
    assert compile_tm_to_runtime_tape is compile_tm_to_encoded_band
    assert pretty_runtime_tape is pretty_outer_tape
    assert "RUNTIME TAPE" in pretty_runtime_tape(band.runtime_tape)
