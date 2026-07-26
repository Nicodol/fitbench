"""Command-line interface for fitbench.

Subcommands (v0 plan, see DESIGN.md):

- ``fitbench split``: seeded held-out split of a verified-patch directory.
- ``fitbench score``: score a run's winding surfaces against held-out patches.
- ``fitbench intrinsic``: ground-truth-free checks only.
- ``fitbench compare``: two runs, same metrics, delta table.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fitbench", description=__doc__)
    parser.add_argument("--version", action="version", version=f"fitbench {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("split", help="seeded held-out split of a verified-patch directory (TODO)")
    sub.add_parser("score", help="score winding surfaces against held-out patches (TODO)")
    sub.add_parser("intrinsic", help="ground-truth-free topology checks (TODO)")
    sub.add_parser("compare", help="compare two runs (TODO)")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(f"fitbench {args.command}: not implemented yet (skeleton)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
