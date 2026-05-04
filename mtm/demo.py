"""Tiny demo entrypoint for exploring MTM fixtures."""

from __future__ import annotations

import argparse

from .fixtures import list_fixtures, load_fixture
from .pretty import pretty_fixture

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show an MTM fixture and its encoded band.")
    parser.add_argument("fixture", nargs="?", default="incrementer")
    parser.add_argument("--list", action="store_true", help="List available fixtures.")
    parser.add_argument("--show-outer", action="store_true", help="Show concrete outer tape addresses too.")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(list_fixtures()))
        return 0

    print(pretty_fixture(load_fixture(args.fixture), show_outer=args.show_outer))
    return 0


__all__ = ["main"]
