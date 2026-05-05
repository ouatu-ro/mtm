"""Read and write MTM artifact files.

Artifacts are plain-text files made of literal assignments. Reading an artifact
parses those literals and validates the declared format; it does not execute
the file as Python code.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .raw_transition_tm import TMTransitionProgram
from .semantic_objects import TMAbi, UTMBandArtifact, UTMProgramArtifact
from .source_encoding import Encoding, abi_from_literal, abi_to_literal

UTM_BAND_FORMAT = "mtm-utm-band-v1"
RAW_TM_FORMAT = "mtm-raw-tm-v1"


def _literal(value) -> str:
    return repr(value)


def _read_literal_assignments(path: str | Path) -> dict[str, object]:
    """Parse a literal-assignment artifact into a namespace dictionary."""

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
    """Reject artifacts whose declared format is not the expected version."""

    actual = namespace.get("format")
    if actual != expected:
        raise ValueError(f"unsupported artifact format: expected {expected!r}, got {actual!r}")


def _load_abi(namespace: dict[str, object], name: str, *, fallback_encoding: Encoding) -> TMAbi:
    data = namespace.get(name)
    if data is None:
        return TMAbi(
            state_width=fallback_encoding.state_width,
            symbol_width=fallback_encoding.symbol_width,
            dir_width=fallback_encoding.direction_width,
            family_label=f"U[Wq={fallback_encoding.state_width},Ws={fallback_encoding.symbol_width},Wd={fallback_encoding.direction_width}]",
        )
    return abi_from_literal(data)


def write_utm_artifact(path: str | Path, artifact: UTMBandArtifact) -> None:
    """Write a ``.utm.band`` artifact from a UTMBandArtifact object."""

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
        f"target_abi = {_literal(abi_to_literal(artifact.target_abi))}",
        f"minimal_abi = {_literal(abi_to_literal(artifact.minimal_abi))}",
    ])
    path.write_text(text + "\n")


def read_utm_artifact(path: str | Path) -> UTMBandArtifact:
    """Read a ``.utm.band`` artifact without executing it."""

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
    """Write a raw universal-machine ``.tm`` artifact."""

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


def write_utm_program_artifact(path: str | Path, artifact: UTMProgramArtifact) -> None:
    """Write a UTM program artifact, including ABI metadata when known."""

    path = Path(path)
    fields = [
        f"format = {RAW_TM_FORMAT!r}",
        f"start_state = {_literal(artifact.program.start_state)}",
        f"halt_state = {_literal(artifact.program.halt_state)}",
        f"blank = {_literal(artifact.program.blank)}",
        f"alphabet = {_literal(list(artifact.program.alphabet))}",
        f"raw_tm = {_literal(artifact.program.prog)}",
    ]
    if artifact.target_abi is not None:
        fields.append(f"target_abi = {_literal(abi_to_literal(artifact.target_abi))}")
    if artifact.minimal_abi is not None:
        fields.append(f"minimal_abi = {_literal(abi_to_literal(artifact.minimal_abi))}")
    path.write_text("\n".join(fields) + "\n")


def read_tm(path: str | Path) -> TMTransitionProgram:
    """Read a raw universal-machine ``.tm`` artifact without executing it."""

    namespace = _read_literal_assignments(path)
    _require_format(namespace, RAW_TM_FORMAT)
    return TMTransitionProgram(
        prog=namespace["raw_tm"],
        start_state=namespace["start_state"],
        halt_state=namespace["halt_state"],
        alphabet=tuple(namespace["alphabet"]),
        blank=namespace["blank"],
    )


def read_utm_program_artifact(path: str | Path) -> UTMProgramArtifact:
    """Read a UTM program artifact, preserving persisted ABI metadata."""

    namespace = _read_literal_assignments(path)
    _require_format(namespace, RAW_TM_FORMAT)
    return UTMProgramArtifact(
        program=TMTransitionProgram(
            prog=namespace["raw_tm"],
            start_state=namespace["start_state"],
            halt_state=namespace["halt_state"],
            alphabet=tuple(namespace["alphabet"]),
            blank=namespace["blank"],
        ),
        target_abi=None if namespace.get("target_abi") is None else abi_from_literal(namespace["target_abi"]),
        minimal_abi=None if namespace.get("minimal_abi") is None else abi_from_literal(namespace["minimal_abi"]),
    )


__all__ = [
    "read_tm",
    "read_utm_artifact",
    "read_utm_program_artifact",
    "write_tm",
    "write_utm_artifact",
    "write_utm_program_artifact",
]
