"""Read and write plain-text artifact files for MTM pipelines."""

from __future__ import annotations

from pathlib import Path
from runpy import run_path

from .compiled_band import EncodedBand
from .raw_tm import RawTM
from .semantic_objects import TMAbi, UTMEncodingArtifact, encoded_band_from_utm_artifact, start_head_from_encoded_band, utm_artifact_from_band
from .tape_encoding import Encoding


def _literal(value) -> str:
    return repr(value)


def _abi_literal(abi: TMAbi) -> dict[str, object]:
    return {
        "state_width": abi.state_width,
        "symbol_width": abi.symbol_width,
        "dir_width": abi.dir_width,
        "grammar_version": abi.grammar_version,
        "family_label": abi.family_label,
    }


def _load_abi(namespace: dict[str, object], name: str, *, fallback_encoding: Encoding) -> TMAbi:
    data = namespace.get(name)
    if data is None:
        return TMAbi(
            state_width=fallback_encoding.state_width,
            symbol_width=fallback_encoding.symbol_width,
            dir_width=fallback_encoding.direction_width,
            family_label=f"U[Wq={fallback_encoding.state_width},Ws={fallback_encoding.symbol_width},Wd={fallback_encoding.direction_width}]",
        )
    return TMAbi(
        state_width=data["state_width"],
        symbol_width=data["symbol_width"],
        dir_width=data["dir_width"],
        grammar_version=data.get("grammar_version", "mtm-v1"),
        family_label=data.get("family_label", ""),
    )


def write_utm_artifact(path: str | Path, artifact: UTMEncodingArtifact) -> None:
    path = Path(path)
    encoding = {
        "state_ids": artifact.encoding.state_ids,
        "symbol_ids": artifact.encoding.symbol_ids,
        "direction_ids": artifact.encoding.direction_ids,
        "state_width": artifact.encoding.state_width,
        "symbol_width": artifact.encoding.symbol_width,
        "direction_width": artifact.encoding.direction_width,
        "blank": artifact.encoding.blank,
        "initial_state": artifact.encoding.initial_state,
        "halt_state": artifact.encoding.halt_state,
    }
    text = "\n".join([
        "format = 'mtm-outer-band-v1'",
        f"start_head = {artifact.start_head!r}",
        f"encoding = {_literal(encoding)}",
        f"left_band = {_literal(list(artifact.left_band))}",
        f"right_band = {_literal(list(artifact.right_band))}",
        f"target_abi = {_literal(_abi_literal(artifact.target_abi))}",
        f"minimal_abi = {_literal(_abi_literal(artifact.minimal_abi))}",
    ])
    path.write_text(text + "\n")


def read_utm_artifact(path: str | Path) -> UTMEncodingArtifact:
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
    return UTMEncodingArtifact(
        encoding=encoding,
        left_band=tuple(namespace["left_band"]),
        right_band=tuple(namespace["right_band"]),
        start_head=namespace["start_head"],
        target_abi=_load_abi(namespace, "target_abi", fallback_encoding=encoding),
        minimal_abi=_load_abi(namespace, "minimal_abi", fallback_encoding=encoding),
    )


def band_start_head(band: EncodedBand) -> int: return start_head_from_encoded_band(band)


def write_utm(path: str | Path, band_or_artifact: EncodedBand | UTMEncodingArtifact) -> None:
    artifact = band_or_artifact if isinstance(band_or_artifact, UTMEncodingArtifact) else utm_artifact_from_band(band_or_artifact)
    write_utm_artifact(path, artifact)


def read_utm(path: str | Path) -> tuple[EncodedBand, int]:
    artifact = read_utm_artifact(path)
    return encoded_band_from_utm_artifact(artifact), artifact.start_head


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


__all__ = [
    "band_start_head",
    "read_tm",
    "read_utm",
    "read_utm_artifact",
    "write_tm",
    "write_utm",
    "write_utm_artifact",
]
