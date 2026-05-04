"""Tiny demo entrypoint for exploring MTM fixtures."""

from __future__ import annotations

import argparse

from .fixtures import list_fixtures, load_fixture

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show an MTM fixture and its encoded band.")
    parser.add_argument("fixture", nargs="?", default="incrementer")
    parser.add_argument("--list", action="store_true", help="List available fixtures.")
    args = parser.parse_args(argv)

    if args.list:
        print("\n".join(list_fixtures()))
        return 0

    print(load_fixture(args.fixture).describe())
    return 0


__all__ = ["main"]
