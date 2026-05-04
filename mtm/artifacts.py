"""Read and write plain-text artifact files for MTM pipelines."""

from __future__ import annotations

from pathlib import Path
from runpy import run_path

from .compiled_band import EncodedBand
from .tape_encoding import Encoding
from .raw_tm import RawTM


def _literal(value) -> str:
    return repr(value)


def band_start_head(band: EncodedBand) -> int:
    left_addresses = list(range(-len(band.left_band), 0))
    return left_addresses[band.left_band.index("#CUR_STATE")]


def write_utm(path: str | Path, band: EncodedBand) -> None:
    path = Path(path)
    encoding = {
        "state_ids": band.encoding.state_ids,
        "symbol_ids": band.encoding.symbol_ids,
        "direction_ids": band.encoding.direction_ids,
        "state_width": band.encoding.state_width,
        "symbol_width": band.encoding.symbol_width,
        "direction_width": band.encoding.direction_width,
        "blank": band.encoding.blank,
        "initial_state": band.encoding.initial_state,
        "halt_state": band.encoding.halt_state,
    }
    text = "\n".join([
        "format = 'mtm-outer-band-v1'",
        f"start_head = {band_start_head(band)!r}",
        f"encoding = {_literal(encoding)}",
        f"left_band = {_literal(band.left_band)}",
        f"right_band = {_literal(band.right_band)}",
    ])
    path.write_text(text + "\n")


def read_utm(path: str | Path) -> tuple[EncodedBand, int]:
    namespace = run_path(str(path))
    encoding_data = namespace["encoding"]
    encoding = Encoding(
        state_ids=encoding_data["state_ids"],
        symbol_ids=encoding_data["symbol_ids"],
        direction_ids=encoding_data["direction_ids"],
        state_width=encoding_data["state_width"],
        symbol_width=encoding_data["symbol_width"],
        direction_width=encoding_data["direction_width"],
        blank=encoding_data["blank"],
        initial_state=encoding_data["initial_state"],
        halt_state=encoding_data["halt_state"],
    )
    left_band, right_band = namespace["left_band"], namespace["right_band"]
    return EncodedBand(encoding, left_band, right_band), namespace["start_head"]


def write_tm(path: str | Path, tm: RawTM) -> None:
    path = Path(path)
    text = "\n".join([
        "format = 'mtm-raw-tm-v1'",
        f"start_state = {_literal(tm.start_state)}",
        f"halt_state = {_literal(tm.halt_state)}",
        f"blank = {_literal(tm.blank)}",
        f"alphabet = {_literal(list(tm.alphabet))}",
        f"raw_tm = {_literal(tm.prog)}",
    ])
    path.write_text(text + "\n")


def read_tm(path: str | Path) -> RawTM:
    namespace = run_path(str(path))
    return RawTM(
        prog=namespace["raw_tm"],
        start_state=namespace["start_state"],
        halt_state=namespace["halt_state"],
        alphabet=tuple(namespace["alphabet"]),
        blank=namespace["blank"],
    )


__all__ = ["band_start_head", "read_tm", "read_utm", "write_tm", "write_utm"]
