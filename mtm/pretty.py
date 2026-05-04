"""Pretty-printers for MTM fixtures and encoded bands.

``pretty_runtime_tape`` is the primary tape printer.
``pretty_outer_tape`` remains a compatibility alias.
"""

from __future__ import annotations

from .compiled_band import (
    CELL,
    CMP_FLAG,
    CUR_STATE,
    CUR_SYMBOL,
    END_CELL,
    END_FIELD,
    END_REGS,
    END_RULE,
    END_RULES,
    END_TAPE,
    HEAD,
    MOVE_DIR,
    MOVE,
    NEXT,
    NEXT_STATE,
    NO_HEAD,
    OUTER_BLANK,
    READ,
    REGS,
    RULE,
    RULES,
    STATE,
    TAPE,
    TMP,
    WRITE,
    WRITE_SYMBOL,
    EncodedBand,
)
from .tape_encoding import Encoding, L, R, encode_direction, encode_state, encode_symbol

RuleRow = tuple[str, str, str, str, int]

def dir_name(direction: int) -> str: return {L: "L", R: "R"}[direction]
def format_bits(bits: tuple[str, ...] | list[str]) -> str: return "".join(bits)


def table(headers: list[str], rows: list[list[object]]) -> str:
    headers = [str(header) for header in headers]
    rows = [[str(value) for value in row] for row in rows]
    widths = [max([len(headers[i])] + [len(row[i]) for row in rows]) for i in range(len(headers))]

    def fmt(row: list[str]) -> str: return " | ".join(row[i].ljust(widths[i]) for i in range(len(headers)))
    return "\n".join([fmt(headers), "-+-".join("-" * width for width in widths), *(fmt(row) for row in rows)])


def section(title: str, *parts: str) -> str: return "\n\n".join([title, *parts])


def take_field(tokens: list[str], index: int, marker: str) -> tuple[tuple[str, ...], int]:
    if tokens[index] != marker:
        raise ValueError(f"expected {marker}, got {tokens[index]!r} at index {index}")
    end = tokens.index(END_FIELD, index + 1)
    return tuple(tokens[index + 1:end]), end + 1


def parse_registers(encoding: Encoding, left_band: list[str]) -> tuple[dict[str, object], int]:
    if not left_band or left_band[0] != REGS:
        raise ValueError("left band does not start with #REGS")

    index, registers = 1, {}
    fields = [
        (CUR_STATE, "CUR_STATE", encoding.id_states),
        (CUR_SYMBOL, "CUR_SYMBOL", encoding.id_symbols),
        (WRITE_SYMBOL, "WRITE_SYMBOL", encoding.id_symbols),
        (NEXT_STATE, "NEXT_STATE", encoding.id_states),
        (MOVE_DIR, "MOVE_DIR", encoding.id_dirs),
    ]
    for marker, name, id_map in fields:
        bits, index = take_field(left_band, index, marker)
        registers[name] = id_map[int(format_bits(bits), 2)]

    cmp_bits, index = take_field(left_band, index, CMP_FLAG)
    tmp_bits, index = take_field(left_band, index, TMP)
    if left_band[index] != END_REGS:
        raise ValueError(f"expected {END_REGS}, got {left_band[index]!r} at index {index}")
    registers["CMP_FLAG"] = cmp_bits[0]
    registers["TMP"] = tmp_bits
    return registers, index + 1


def parse_rules(encoding: Encoding, left_band: list[str], start: int) -> list[RuleRow]:
    if left_band[start] != RULES:
        raise ValueError(f"expected {RULES}, got {left_band[start]!r} at index {start}")

    index, rules = start + 1, []
    while left_band[index] != END_RULES:
        if left_band[index] != RULE:
            raise ValueError(f"expected {RULE}, got {left_band[index]!r} at index {index}")
        index += 1
        state_bits, index = take_field(left_band, index, STATE)
        read_bits, index = take_field(left_band, index, READ)
        write_bits, index = take_field(left_band, index, WRITE)
        next_bits, index = take_field(left_band, index, NEXT)
        move_bits, index = take_field(left_band, index, MOVE)
        if left_band[index] != END_RULE:
            raise ValueError(f"expected {END_RULE}, got {left_band[index]!r} at index {index}")
        rules.append((
            encoding.id_states[int(format_bits(state_bits), 2)],
            encoding.id_symbols[int(format_bits(read_bits), 2)],
            encoding.id_states[int(format_bits(next_bits), 2)],
            encoding.id_symbols[int(format_bits(write_bits), 2)],
            encoding.id_dirs[int(format_bits(move_bits), 2)],
        ))
        index += 1
    return rules


def parse_tape(encoding: Encoding, right_band: list[str]) -> tuple[list[str], int]:
    if not right_band or right_band[0] != TAPE:
        raise ValueError("right band does not start with #TAPE")

    index, cells, head_index = 1, [], None
    while right_band[index] != END_TAPE:
        if right_band[index] != CELL:
            raise ValueError(f"expected {CELL}, got {right_band[index]!r} at index {index}")
        head_flag = right_band[index + 1]
        symbol_bits = tuple(right_band[index + 2:index + 2 + encoding.symbol_width])
        if right_band[index + 2 + encoding.symbol_width] != END_CELL:
            raise ValueError(f"expected {END_CELL}, got {right_band[index + 2 + encoding.symbol_width]!r} at index {index}")
        if head_flag == HEAD:
            if head_index is not None:
                raise ValueError("multiple simulated heads")
            head_index = len(cells)
        elif head_flag != NO_HEAD:
            raise ValueError(f"bad head flag: {head_flag!r}")
        cells.append(encoding.id_symbols[int(format_bits(symbol_bits), 2)])
        index += 3 + encoding.symbol_width

    if head_index is None:
        raise ValueError("no simulated head")
    return cells, head_index


def pretty_encoding(encoding: Encoding) -> str:
    state_rows = [[state, index, format_bits(encode_state(encoding, state))] for state, index in encoding.state_ids.items()]
    symbol_rows = [[repr(symbol), index, format_bits(encode_symbol(encoding, symbol))] for symbol, index in encoding.symbol_ids.items()]
    direction_rows = [[dir_name(direction), index, format_bits(encode_direction(encoding, direction))] for direction, index in encoding.direction_ids.items()]
    return section(
        "ENCODING",
        table(["state", "id", "bits"], state_rows),
        table(["symbol", "id", "bits"], symbol_rows),
        table(["direction", "id", "bits"], direction_rows),
    )


def pretty_registers(encoding: Encoding, left_band: list[str]) -> str:
    registers, _ = parse_registers(encoding, left_band)
    rows = [
        ["CUR_STATE", repr(registers["CUR_STATE"]), format_bits(encode_state(encoding, registers["CUR_STATE"]))],
        ["CUR_SYMBOL", repr(registers["CUR_SYMBOL"]), format_bits(encode_symbol(encoding, registers["CUR_SYMBOL"]))],
        ["WRITE_SYMBOL", repr(registers["WRITE_SYMBOL"]), format_bits(encode_symbol(encoding, registers["WRITE_SYMBOL"]))],
        ["NEXT_STATE", repr(registers["NEXT_STATE"]), format_bits(encode_state(encoding, registers["NEXT_STATE"]))],
        ["MOVE_DIR", dir_name(registers["MOVE_DIR"]), format_bits(encode_direction(encoding, registers["MOVE_DIR"]))],
        ["CMP_FLAG", registers["CMP_FLAG"], registers["CMP_FLAG"]],
        ["TMP", format_bits(registers["TMP"]), format_bits(registers["TMP"])],
    ]
    return section("REGISTERS", table(["register", "decoded", "bits"], rows))


def pretty_rules(encoding: Encoding, left_band: list[str]) -> str:
    _, start = parse_registers(encoding, left_band)
    rows = []
    for index, (state, read, next_state, write, move) in enumerate(parse_rules(encoding, left_band, start)):
        rows.append([
            index,
            repr(state), format_bits(encode_state(encoding, state)),
            repr(read), format_bits(encode_symbol(encoding, read)),
            repr(write), format_bits(encode_symbol(encoding, write)),
            repr(next_state), format_bits(encode_state(encoding, next_state)),
            dir_name(move), format_bits(encode_direction(encoding, move)),
        ])
    return section(
        "RULES",
        table(["idx", "state", "state_bits", "read", "read_bits", "write", "write_bits", "next", "next_bits", "move", "move_bits"], rows),
    )


def pretty_tape(encoding: Encoding, right_band: list[str]) -> str:
    cells, head = parse_tape(encoding, right_band)
    rows = [[index, "yes" if index == head else "no", repr(symbol), format_bits(encode_symbol(encoding, symbol))] for index, symbol in enumerate(cells)]
    visual_symbols = " ".join(cells)
    visual_head = " ".join("^" if index == head else " " for index in range(len(cells)))
    return section("TAPE", table(["cell", "head", "symbol", "bits"], rows), visual_symbols, visual_head)


def pretty_raw_tape(raw_tape: dict[int, str]) -> str:
    live = [address for address, value in raw_tape.items() if value != OUTER_BLANK]
    rows = [[address, "left" if address < 0 else "right", raw_tape[address]] for address in range(min(live), max(live) + 1)]
    return section("RUNTIME TAPE", table(["addr", "side", "value"], rows))


def pretty_runtime_tape(runtime_tape: dict[int, str]) -> str: return pretty_raw_tape(runtime_tape)


def pretty_outer_tape(outer_tape: dict[int, str]) -> str:
    """Compatibility alias for pretty_runtime_tape()."""
    return pretty_runtime_tape(outer_tape)


def pretty_band(band: EncodedBand, *, show_runtime: bool = False, show_outer: bool | None = None) -> str:
    show_runtime = show_runtime or bool(show_outer)
    parts = [
        pretty_encoding(band.encoding),
        pretty_registers(band.encoding, band.left_band),
        pretty_rules(band.encoding, band.left_band),
        pretty_tape(band.encoding, band.right_band),
    ]
    if show_runtime:
        parts.append(pretty_runtime_tape(band.runtime_tape))
    return ("\n\n" + "=" * 88 + "\n\n").join(parts)


def pretty_fixture(fixture, *, show_runtime: bool = False, show_outer: bool | None = None) -> str:
    band = fixture.build_band()
    show_runtime = show_runtime or bool(show_outer)
    summary = section(
        "FIXTURE",
        table(
            ["field", "value"],
            [
                ["name", fixture.name],
                ["note", fixture.note or "-"],
                ["input", "".join(fixture.input_symbols)],
                ["states", len(band.encoding.state_ids)],
                ["symbols", len(band.encoding.symbol_ids)],
                ["rules", len(fixture.tm_program)],
            ],
        ),
    )
    return summary + "\n\n" + "=" * 88 + "\n\n" + pretty_band(band, show_runtime=show_runtime)


__all__ = [
    "dir_name",
    "format_bits",
    "parse_registers",
    "parse_rules",
    "parse_tape",
    "pretty_band",
    "pretty_encoding",
    "pretty_fixture",
    "pretty_raw_tape",
    "pretty_runtime_tape",
    "pretty_outer_tape",
    "pretty_registers",
    "pretty_rules",
    "pretty_tape",
    "section",
    "table",
]
