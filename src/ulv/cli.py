"""Command-line interface for Unladen Velocity."""

import argparse

from ulv import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ulv",
        description=(
            "Generate self-contained static HTML sites from existing "
            "benchmark result data."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
