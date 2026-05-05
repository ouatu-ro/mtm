"""Read and write plain-text artifact files for MTM pipelines."""

from __future__ import annotations

import ast
from pathlib import Path

from .raw_transition_tm import TMTransitionProgram
from .semantic_objects import TMAbi, UTMBandArtifact
from .source_encoding import Encoding

UTM_BAND_FORMAT = "mtm-utm-band-v1"
RAW_TM_FORMAT = "mtm-raw-tm-v1"


def _literal(value) -> str:
    return repr(value)


def _read_literal_assignments(path: str | Path) -> dict[str, object]:
    path = Path(path)
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"{path} is not a valid MTM artifact") from exc

    namespace: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise ValueError("MTM artifact may contain only simple literal assignments")
        name = node.targets[0].id
        if name in namespace:
            raise ValueError(f"duplicate artifact field: {name}")
        try:
            namespace[name] = ast.literal_eval(node.value)
        except (SyntaxError, TypeError, ValueError) as exc:
            raise ValueError(f"artifact field `{name}` must be a Python literal") from exc
    return namespace


def _require_format(namespace: dict[str, object], expected: str) -> None:
    actual = namespace.get("format")
    if actual != expected:
        raise ValueError(f"unsupported artifact format: expected {expected!r}, got {actual!r}")


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


def write_utm_artifact(path: str | Path, artifact: UTMBandArtifact) -> None:
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
        f"format = {UTM_BAND_FORMAT!r}",
        f"start_head = {artifact.start_head!r}",
        f"encoding = {_literal(encoding)}",
        f"left_band = {_literal(list(artifact.left_band))}",
        f"right_band = {_literal(list(artifact.right_band))}",
        f"target_abi = {_literal(_abi_literal(artifact.target_abi))}",
        f"minimal_abi = {_literal(_abi_literal(artifact.minimal_abi))}",
    ])
    path.write_text(text + "\n")


def read_utm_artifact(path: str | Path) -> UTMBandArtifact:
    namespace = _read_literal_assignments(path)
    _require_format(namespace, UTM_BAND_FORMAT)
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
    return UTMBandArtifact(
        encoding=encoding,
        left_band=tuple(namespace["left_band"]),
        right_band=tuple(namespace["right_band"]),
        start_head=namespace["start_head"],
        target_abi=_load_abi(namespace, "target_abi", fallback_encoding=encoding),
        minimal_abi=_load_abi(namespace, "minimal_abi", fallback_encoding=encoding),
    )


def write_tm(path: str | Path, tm: TMTransitionProgram) -> None:
    path = Path(path)
    text = "\n".join([
        f"format = {RAW_TM_FORMAT!r}",
        f"start_state = {_literal(tm.start_state)}",
        f"halt_state = {_literal(tm.halt_state)}",
        f"blank = {_literal(tm.blank)}",
        f"alphabet = {_literal(list(tm.alphabet))}",
        f"raw_tm = {_literal(tm.prog)}",
    ])
    path.write_text(text + "\n")


def read_tm(path: str | Path) -> TMTransitionProgram:
    namespace = _read_literal_assignments(path)
    _require_format(namespace, RAW_TM_FORMAT)
    return TMTransitionProgram(
        prog=namespace["raw_tm"],
        start_state=namespace["start_state"],
        halt_state=namespace["halt_state"],
        alphabet=tuple(namespace["alphabet"]),
        blank=namespace["blank"],
    )


__all__ = [
    "read_tm",
    "read_utm_artifact",
    "write_tm",
    "write_utm_artifact",
]
