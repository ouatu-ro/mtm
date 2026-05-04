"""Readable building blocks for the Meta Turing Machine experiment."""

from .artifacts import read_tm, read_utm, read_utm_artifact, write_tm, write_utm, write_utm_artifact
from .cli import main as cli_main
from .compiled_band import (
    EncodedBand,
    build_encoded_band,
    build_outer_tape,
    compile_tm_to_universal_tape,
    materialize_raw_tape,
    materialize_runtime_tape,
    split_outer_tape,
    split_raw_tape,
    split_runtime_tape,
)
from .fixtures import TMFixture, get_fixture, list_fixtures, load_fixture
from .lowering import lower_instruction, lower_instruction_sequence, lower_program, lower_program_to_raw_tm
from .meta_asm import Block, Program, Unimplemented, build_universal_meta_asm, format_program
from .meta_asm_host import (
    MetaInterpreterRules,
    build_meta_interpreter_rules,
    format_meta_trace,
    run_meta_asm_block,
    run_meta_asm_block_runtime,
    run_meta_asm_host,
    run_meta_asm_runtime,
)
from .pretty import pretty_band, pretty_fixture, pretty_outer_tape, pretty_runtime_tape
from .program_input import load_python_tm, load_python_tm_instance
from .raw_tm import RawTM, TMBuilder, format_raw_tm, run_raw_tm
from .semantic_objects import (
    AbiRequirement,
    DecodedBandView,
    RawTMConfig,
    TMBand,
    TMAbi,
    TMInstance,
    UTMEncoded,
    UTMEncodedRule,
    UTMEncodingArtifact,
    UTMRegisters,
    UTMSimulatedTape,
    abi_from_encoding,
    decoded_view_from_encoded_band,
    encoded_band_from_utm_artifact,
    infer_minimal_abi,
    source_band_from_simulated_tape,
    start_head_from_encoded_band,
    utm_artifact_from_band,
    utm_encoded_from_band,
)
from .tape_encoding import Encoding

def build_utm_encoded(*args, **kwargs):
    """Compatibility wrapper for :func:`utm_encoded_from_band`."""
    return utm_encoded_from_band(*args, **kwargs)


def build_utm_encoding_artifact(*args, **kwargs):
    """Compatibility wrapper for :func:`utm_artifact_from_band`."""
    return utm_artifact_from_band(*args, **kwargs)


# Compatibility aliases kept for downstream callers while the runtime-tape
# and universal-tape names are the primary public surface.
build_runtime_tape = build_outer_tape
compile_tm_to_runtime_tape = compile_tm_to_universal_tape
compile_tm_to_encoded_band = compile_tm_to_runtime_tape
pretty_outer_tape = pretty_runtime_tape

__all__ = [
    "EncodedBand",
    "Encoding",
    "MetaInterpreterRules",
    "Block",
    "Program",
    "AbiRequirement",
    "DecodedBandView",
    "RawTM",
    "RawTMConfig",
    "TMFixture",
    "TMBand",
    "TMAbi",
    "TMInstance",
    "TMBuilder",
    "build_utm_encoded",
    "build_utm_encoding_artifact",
    "UTMEncoded",
    "UTMEncodedRule",
    "UTMEncodingArtifact",
    "UTMRegisters",
    "UTMSimulatedTape",
    "Unimplemented",
    "abi_from_encoding",
    "build_meta_interpreter_rules",
    "build_encoded_band",
    "build_universal_meta_asm",
    "build_runtime_tape",
    "build_outer_tape",
    "cli_main",
    "compile_tm_to_encoded_band",
    "compile_tm_to_runtime_tape",
    "compile_tm_to_universal_tape",
    "format_meta_trace",
    "format_program",
    "get_fixture",
    "list_fixtures",
    "lower_instruction",
    "lower_instruction_sequence",
    "lower_program",
    "lower_program_to_raw_tm",
    "load_fixture",
    "load_python_tm",
    "load_python_tm_instance",
    "materialize_runtime_tape",
    "materialize_raw_tape",
    "pretty_band",
    "pretty_fixture",
    "pretty_outer_tape",
    "pretty_runtime_tape",
    "read_tm",
    "read_utm",
    "read_utm_artifact",
    "format_raw_tm",
    "run_meta_asm_block",
    "run_meta_asm_block_runtime",
    "run_raw_tm",
    "run_meta_asm_host",
    "run_meta_asm_runtime",
    "split_runtime_tape",
    "split_raw_tape",
    "split_outer_tape",
    "decoded_view_from_encoded_band",
    "encoded_band_from_utm_artifact",
    "infer_minimal_abi",
    "source_band_from_simulated_tape",
    "start_head_from_encoded_band",
    "utm_artifact_from_band",
    "utm_encoded_from_band",
    "write_tm",
    "write_utm",
    "write_utm_artifact",
]
