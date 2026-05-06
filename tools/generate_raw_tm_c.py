"""Emit a self-contained C runner for one raw ``.tm`` and ``.utm.band`` pair."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from mtm.semantic_objects import UTMBandArtifact, UTMProgramArtifact
from mtm.utm_band_layout import CELL, END_CELL, HEAD, NO_HEAD


@dataclass(frozen=True)
class CData:
    state_ids: dict[str, int]
    symbol_ids: dict[str, int]
    table_next: list[int]
    table_write: list[int]
    table_move_code: list[int]
    init: list[tuple[int, int]]
    origin: int
    tape_size: int
    right_token_count: int
    right_dump_cells: int
    raw_dump_cells: int
    start_state: int
    halt_state: int
    start_head: int
    blank: int
    source_symbols: tuple[str, ...]
    source_symbol_width: int

    @property
    def state_count(self) -> int:
        return len(self.state_ids)

    @property
    def symbol_count(self) -> int:
        return len(self.symbol_ids)

    @property
    def table_size(self) -> int:
        return self.state_count * self.symbol_count


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit a self-contained C runner for a raw TM artifact.")
    parser.add_argument("tm_file", help="Path to a raw .tm artifact.")
    parser.add_argument("band_file", help="Path to the initial .utm.band artifact.")
    parser.add_argument("-o", "--output", required=True, help="Output .c path.")
    parser.add_argument("--backend", choices=("packed-array", "computed-goto"), default="packed-array")
    parser.add_argument("--margin", type=int, default=1000, help="Blank fixed-tape margin on both sides.")
    parser.add_argument("--right-dump-cells", type=int, default=None, help="How many decoded nonnegative cells to print.")
    parser.add_argument("--raw-dump-cells", type=int, default=0, help="How many raw nonnegative tape cells to print.")
    return parser


def _c_string(value: str) -> str:
    return json.dumps(value)


def _array(name: str, values: list[int] | tuple[int, ...], *, ctype: str = "int") -> list[str]:
    lines = [f"static const {ctype} {name}[] = {{"]
    row: list[str] = []
    for value in values:
        row.append(str(value))
        if len(row) == 24:
            lines.append("  " + ", ".join(row) + ",")
            row = []
    if row:
        lines.append("  " + ", ".join(row) + ",")
    lines.append("};")
    return lines


def _packed_array(name: str, next_values: list[int], write_values: list[int], move_codes: list[int]) -> list[str]:
    lines = [f"static const uint64_t {name}[] = {{"]
    row: list[str] = []
    for next_state, write_symbol, move_code in zip(next_values, write_values, move_codes, strict=True):
        if next_state < 0:
            value = "0ULL"
        else:
            packed = (1 << 63) | (move_code << 48) | (write_symbol << 32) | next_state
            value = f"{packed}ULL"
        row.append(value)
        if len(row) == 8:
            lines.append("  " + ", ".join(row) + ",")
            row = []
    if row:
        lines.append("  " + ", ".join(row) + ",")
    lines.append("};")
    return lines


def _token_define_name(token: str) -> str:
    names = {
        "0": "TOK_0",
        "1": "TOK_1",
        CELL: "TOK_CELL",
        HEAD: "TOK_HEAD",
        NO_HEAD: "TOK_NO_HEAD",
        END_CELL: "TOK_END_CELL",
    }
    return names[token]


def _collect_data(tm_file: Path, band_file: Path, *, margin: int, right_dump_cells: int | None, raw_dump_cells: int) -> CData:
    program_artifact = UTMProgramArtifact.read(tm_file)
    program = program_artifact.program
    band = UTMBandArtifact.read(band_file)
    runtime_tape = band.to_runtime_tape()

    states = {program.start_state, program.halt_state}
    symbols = set(program.alphabet) | set(runtime_tape.values()) | {program.blank}
    for (state, read_symbol), (next_state, write_symbol, _move) in program.transitions.items():
        states.update((state, next_state))
        symbols.update((read_symbol, write_symbol))

    state_ids = {state: index for index, state in enumerate(sorted(states))}
    symbol_ids = {symbol: index for index, symbol in enumerate(sorted(symbols))}
    table_size = len(state_ids) * len(symbol_ids)
    table_next = [-1] * table_size
    table_write = [0] * table_size
    table_move_code = [1] * table_size
    for (state, read_symbol), (next_state, write_symbol, move) in program.transitions.items():
        offset = state_ids[state] * len(symbol_ids) + symbol_ids[read_symbol]
        table_next[offset] = state_ids[next_state]
        table_write[offset] = symbol_ids[write_symbol]
        table_move_code[offset] = move + 1

    low, high = min(runtime_tape), max(runtime_tape)
    origin = margin - low
    tape_size = (high - low + 1) + margin * 2
    init = [(address + origin, symbol_ids[symbol]) for address, symbol in sorted(runtime_tape.items())]
    dump_cells = len(band.right_band) if right_dump_cells is None else right_dump_cells
    return CData(
        state_ids=state_ids,
        symbol_ids=symbol_ids,
        table_next=table_next,
        table_write=table_write,
        table_move_code=table_move_code,
        init=init,
        origin=origin,
        tape_size=tape_size,
        right_token_count=len(band.right_band),
        right_dump_cells=dump_cells,
        raw_dump_cells=raw_dump_cells,
        start_state=state_ids[program.start_state],
        halt_state=state_ids[program.halt_state],
        start_head=band.start_head + origin,
        blank=symbol_ids[program.blank],
        source_symbols=tuple(band.encoding.id_symbols[index] for index in range(len(band.encoding.id_symbols))),
        source_symbol_width=band.encoding.symbol_width,
    )


def _common_preamble(data: CData, *, backend: str) -> list[str]:
    symbol_type = "uint8_t" if data.symbol_count <= 255 else "uint16_t"
    lines = [
        "/* Generated by tools/generate_raw_tm_c.py. */",
        "#include <stdint.h>",
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "#include <time.h>",
        "",
        f"#define BACKEND {_c_string(backend)}",
        f"#define TAPE_SIZE {data.tape_size}",
        f"#define STATE_COUNT {data.state_count}",
        f"#define SYMBOL_COUNT {data.symbol_count}",
        f"#define TABLE_SIZE {data.table_size}",
        f"#define INIT_COUNT {len(data.init)}",
        f"#define ORIGIN {data.origin}",
        f"#define BLANK {data.blank}",
        f"#define HALT {data.halt_state}",
        f"#define START_STATE {data.start_state}",
        f"#define START_HEAD {data.start_head}",
        f"#define RIGHT_TOKEN_COUNT {data.right_token_count}",
        f"#define RIGHT_DUMP_CELLS {data.right_dump_cells}",
        f"#define RAW_DUMP_CELLS {data.raw_dump_cells}",
        f"#define SOURCE_SYMBOL_COUNT {len(data.source_symbols)}",
        f"#define SOURCE_SYMBOL_WIDTH {data.source_symbol_width}",
        f"typedef {symbol_type} Symbol;",
    ]
    for token in ("0", "1", CELL, HEAD, NO_HEAD, END_CELL):
        if token in data.symbol_ids:
            lines.append(f"#define {_token_define_name(token)} {data.symbol_ids[token]}")
    lines.append("")
    lines.append("static const char *STATES[] = {")
    for state, _index in sorted(data.state_ids.items(), key=lambda item: item[1]):
        lines.append(f"  {_c_string(state)},")
    lines.append("};")
    lines.append("static const char *SYMBOLS[] = {")
    for symbol, _index in sorted(data.symbol_ids.items(), key=lambda item: item[1]):
        lines.append(f"  {_c_string(symbol)},")
    lines.append("};")
    lines.append("static const char *SOURCE_SYMBOLS[] = {")
    for symbol in data.source_symbols:
        lines.append(f"  {_c_string(symbol)},")
    lines.append("};")
    lines.append("static const int INIT[][2] = {")
    for address, symbol in data.init:
        lines.append(f"  {{{address}, {symbol}}},")
    lines.append("};")
    return lines


def _common_runtime() -> list[str]:
    return [
        "",
        "static long long parse_max_steps(int argc, char **argv) {",
        "  if (argc < 2) return -1;",
        "  char *end = NULL;",
        "  long long value = strtoll(argv[1], &end, 10);",
        "  if (end == argv[1] || *end != '\\0' || value < 0) {",
        "    fprintf(stderr, \"usage: %s [max_steps]\\n\", argv[0]);",
        "    exit(2);",
        "  }",
        "  return value;",
        "}",
        "",
        "static Symbol *init_tape(void) {",
        "  Symbol *tape = malloc(sizeof(Symbol) * TAPE_SIZE);",
        "  if (tape == NULL) {",
        "    fprintf(stderr, \"failed to allocate tape\\n\");",
        "    exit(2);",
        "  }",
        "  for (int i = 0; i < TAPE_SIZE; i++) tape[i] = BLANK;",
        "  for (int i = 0; i < INIT_COUNT; i++) tape[INIT[i][0]] = (Symbol)INIT[i][1];",
        "  return tape;",
        "}",
        "",
        "static int decode_source_symbol(const Symbol *tape, int bits_start) {",
        "  int value = 0;",
        "  for (int i = 0; i < SOURCE_SYMBOL_WIDTH; i++) {",
        "    Symbol token = tape[bits_start + i];",
        "    if (token == TOK_0) value = value << 1;",
        "    else if (token == TOK_1) value = (value << 1) | 1;",
        "    else return -1;",
        "  }",
        "  return value;",
        "}",
        "",
        "static void dump_decoded_right_tape(const Symbol *tape) {",
        "  printf(\"decoded_right:\");",
        "  int raw = 0;",
        "  int cells = 0;",
        "  while (raw < RIGHT_TOKEN_COUNT && cells < RIGHT_DUMP_CELLS) {",
        "    int address = raw + ORIGIN;",
        "    if (address + 2 + SOURCE_SYMBOL_WIDTH >= TAPE_SIZE || tape[address] != TOK_CELL) {",
        "      raw++;",
        "      continue;",
        "    }",
        "    int symbol_id = decode_source_symbol(tape, address + 2);",
        "    if (symbol_id >= 0 && symbol_id < SOURCE_SYMBOL_COUNT) printf(\" %s\", SOURCE_SYMBOLS[symbol_id]);",
        "    else printf(\" <bad-symbol-%d>\", symbol_id);",
        "    raw += 3 + SOURCE_SYMBOL_WIDTH;",
        "    cells++;",
        "  }",
        "  printf(\"\\n\");",
        "}",
        "",
        "static void dump_raw_right_tape(const Symbol *tape) {",
        "  if (RAW_DUMP_CELLS <= 0) return;",
        "  printf(\"raw_right:\");",
        "  for (int raw = 0; raw < RAW_DUMP_CELLS; raw++) {",
        "    int address = raw + ORIGIN;",
        "    if (address < 0 || address >= TAPE_SIZE) printf(\" <out>\");",
        "    else printf(\" %s\", SYMBOLS[tape[address]]);",
        "  }",
        "  printf(\"\\n\");",
        "}",
        "",
        "static void print_result(const char *status, long long steps, int head, int state, clock_t start_clock, const Symbol *tape) {",
        "  double seconds = (double)(clock() - start_clock) / CLOCKS_PER_SEC;",
        "  printf(\"backend=%s status=%s steps=%lld head=%d raw_head=%d state=%s seconds=%.6f msteps_per_s=%.3f\\n\",",
        "         BACKEND, status, steps, head, head - ORIGIN, STATES[state], seconds, seconds > 0 ? (steps / seconds) / 1000000.0 : 0.0);",
        "  dump_decoded_right_tape(tape);",
        "  dump_raw_right_tape(tape);",
        "}",
    ]


def _emit_packed_array(data: CData) -> str:
    lines = _common_preamble(data, backend="packed-array")
    lines.extend(_packed_array("TRANSITIONS", data.table_next, data.table_write, data.table_move_code))
    lines.extend(_common_runtime())
    lines.extend([
        "",
        "#define TRANSITION_VALID(entry) ((entry) >> 63)",
        "#define TRANSITION_NEXT(entry) ((int)((entry) & 0xffffffffULL))",
        "#define TRANSITION_WRITE(entry) ((Symbol)(((entry) >> 32) & 0xffffULL))",
        "#define TRANSITION_MOVE(entry) ((int)(((entry) >> 48) & 0x3ULL) - 1)",
        "",
        "int main(int argc, char **argv) {",
        "  long long max_steps = parse_max_steps(argc, argv);",
        "  Symbol *tape = init_tape();",
        "  int state = START_STATE;",
        "  int head = START_HEAD;",
        "  long long steps = 0;",
        "  clock_t start_clock = clock();",
        "  while (state != HALT) {",
        "    if (max_steps >= 0 && steps >= max_steps) {",
        "      print_result(\"fuel_exhausted\", steps, head, state, start_clock, tape);",
        "      free(tape);",
        "      return 0;",
        "    }",
        "    if (head < 0 || head >= TAPE_SIZE) {",
        "      fprintf(stderr, \"head out of range: head=%d raw_head=%d steps=%lld state=%s\\n\", head, head - ORIGIN, steps, STATES[state]);",
        "      free(tape);",
        "      return 3;",
        "    }",
        "    Symbol read = tape[head];",
        "    uint64_t entry = TRANSITIONS[state * SYMBOL_COUNT + read];",
        "    if (!TRANSITION_VALID(entry)) {",
        "      fprintf(stderr, \"stuck state=%s read=%s head=%d raw_head=%d steps=%lld\\n\", STATES[state], SYMBOLS[read], head, head - ORIGIN, steps);",
        "      dump_decoded_right_tape(tape);",
        "      dump_raw_right_tape(tape);",
        "      free(tape);",
        "      return 4;",
        "    }",
        "    tape[head] = TRANSITION_WRITE(entry);",
        "    state = TRANSITION_NEXT(entry);",
        "    head += TRANSITION_MOVE(entry);",
        "    steps++;",
        "  }",
        "  print_result(\"halted\", steps, head, state, start_clock, tape);",
        "  free(tape);",
        "  return 0;",
        "}",
    ])
    return "\n".join(lines) + "\n"


def _label_name(offset: int) -> str:
    return f"T_{offset}"


def _emit_computed_goto(data: CData) -> str:
    lines = _common_preamble(data, backend="computed-goto")
    lines.extend(_common_runtime())
    lines.extend([
        "",
        "int main(int argc, char **argv) {",
        "  long long max_steps = parse_max_steps(argc, argv);",
        "  Symbol *tape = init_tape();",
        "  int state = START_STATE;",
        "  int head = START_HEAD;",
        "  long long steps = 0;",
        "  clock_t start_clock = clock();",
        "  void **dispatch = calloc(TABLE_SIZE, sizeof(void *));",
        "  if (dispatch == NULL) {",
        "    fprintf(stderr, \"failed to allocate dispatch table\\n\");",
        "    free(tape);",
        "    return 2;",
        "  }",
    ])
    for offset, next_state in enumerate(data.table_next):
        if next_state >= 0:
            lines.append(f"  dispatch[{offset}] = &&{_label_name(offset)};")
    lines.extend([
        "  #define DISPATCH() do { \\",
        "    if (state == HALT) goto halted; \\",
        "    if (max_steps >= 0 && steps >= max_steps) goto fuel_exhausted; \\",
        "    if (head < 0 || head >= TAPE_SIZE) goto head_out_of_range; \\",
        "    Symbol read = tape[head]; \\",
        "    void *target = dispatch[state * SYMBOL_COUNT + read]; \\",
        "    if (target == NULL) goto stuck; \\",
        "    goto *target; \\",
        "  } while (0)",
        "  DISPATCH();",
    ])
    for offset, next_state in enumerate(data.table_next):
        if next_state < 0:
            continue
        lines.extend([
            f"{_label_name(offset)}:",
            f"  tape[head] = (Symbol){data.table_write[offset]};",
            f"  state = {next_state};",
            f"  head += {data.table_move_code[offset] - 1};",
            "  steps++;",
            "  DISPATCH();",
        ])
    lines.extend([
        "halted:",
        "  print_result(\"halted\", steps, head, state, start_clock, tape);",
        "  free(dispatch);",
        "  free(tape);",
        "  return 0;",
        "fuel_exhausted:",
        "  print_result(\"fuel_exhausted\", steps, head, state, start_clock, tape);",
        "  free(dispatch);",
        "  free(tape);",
        "  return 0;",
        "head_out_of_range:",
        "  fprintf(stderr, \"head out of range: head=%d raw_head=%d steps=%lld state=%s\\n\", head, head - ORIGIN, steps, STATES[state]);",
        "  free(dispatch);",
        "  free(tape);",
        "  return 3;",
        "stuck:",
        "  fprintf(stderr, \"stuck state=%s read=%s head=%d raw_head=%d steps=%lld\\n\", STATES[state], SYMBOLS[tape[head]], head, head - ORIGIN, steps);",
        "  dump_decoded_right_tape(tape);",
        "  dump_raw_right_tape(tape);",
        "  free(dispatch);",
        "  free(tape);",
        "  return 4;",
        "}",
    ])
    return "\n".join(lines) + "\n"


def emit_c(data: CData, *, backend: str) -> str:
    if backend == "packed-array":
        return _emit_packed_array(data)
    if backend == "computed-goto":
        return _emit_computed_goto(data)
    raise ValueError(f"unknown backend {backend!r}")


def main() -> int:
    args = _build_parser().parse_args()
    if args.margin < 0:
        raise SystemExit("--margin must be nonnegative")
    if args.right_dump_cells is not None and args.right_dump_cells < 0:
        raise SystemExit("--right-dump-cells must be nonnegative")
    if args.raw_dump_cells < 0:
        raise SystemExit("--raw-dump-cells must be nonnegative")

    data = _collect_data(
        Path(args.tm_file),
        Path(args.band_file),
        margin=args.margin,
        right_dump_cells=args.right_dump_cells,
        raw_dump_cells=args.raw_dump_cells,
    )
    Path(args.output).write_text(emit_c(data, backend=args.backend))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
