from mtm import (
    TMAbi,
    TMBand,
    decoded_view_from_encoded_band,
    load_fixture,
    source_band_from_simulated_tape,
    utm_artifact_from_band,
    utm_encoded_from_band,
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

    assert encoded.current_state == "qFindMargin"
    assert encoded.simulated_head == 0
    assert encoded.target_abi == TMAbi(2, 2, 1, "mtm-v1", "U[Wq=2,Ws=2,Wd=1]")
    assert encoded.minimal_abi == minimal_abi
    assert artifact.target_abi == encoded.target_abi
    assert artifact.minimal_abi == minimal_abi
    assert artifact.left_band[0] == "#REGS"
    assert artifact.right_band[0] == "#TAPE"
    assert artifact.start_head < 0


def test_source_band_helper() -> None:
    band = source_band_from_simulated_tape(("1", "0", "1", "1"), 0, blank="_")
    assert band == TMBand(cells=("1", "0", "1", "1"), head=0, blank="_")
