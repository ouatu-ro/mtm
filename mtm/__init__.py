"""Readable building blocks for the Meta Turing Machine experiment."""

from .artifacts import read_tm, read_utm, write_tm, write_utm
from .cli import main as cli_main
from .compiled_band import EncodedBand, build_outer_tape, compile_tm_to_universal_tape
from .fixtures import TMFixture, get_fixture, list_fixtures, load_fixture
from .lowering import lower_instruction, lower_instruction_sequence, lower_program, lower_program_to_raw_tm
from .meta_asm import Block, Program, Unimplemented, build_universal_meta_asm, format_program
from .meta_asm_host import MetaInterpreterRules, build_meta_interpreter_rules, format_meta_trace, run_meta_asm_block, run_meta_asm_host
from .pretty import pretty_band, pretty_fixture
from .program_input import load_python_tm
from .raw_tm import RawTM, TMBuilder, format_raw_tm, run_raw_tm
from .tape_encoding import Encoding

__all__ = [
    "EncodedBand",
    "Encoding",
    "MetaInterpreterRules",
    "Block",
    "Program",
    "RawTM",
    "TMFixture",
    "TMBuilder",
    "Unimplemented",
    "build_meta_interpreter_rules",
    "build_universal_meta_asm",
    "build_outer_tape",
    "cli_main",
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
    "pretty_band",
    "pretty_fixture",
    "read_tm",
    "read_utm",
    "format_raw_tm",
    "run_meta_asm_block",
    "run_raw_tm",
    "run_meta_asm_host",
    "write_tm",
    "write_utm",
]
