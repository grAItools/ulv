"""Command-line interface for Unladen Velocity."""

import argparse
import sys
from pathlib import Path

from ulv import __version__, plugins
from ulv.errors import UlvError


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
    subparsers = parser.add_subparsers(dest="command")

    build = subparsers.add_parser(
        "build",
        help="generate a static site from benchmark results",
        description="Read benchmark results and generate a static HTML site.",
    )
    build.add_argument(
        "-i",
        "--input-format",
        required=True,
        help="input format name (e.g. 'asv')",
    )
    build.add_argument(
        "--input-dir",
        required=True,
        help="directory containing the benchmark result data",
    )
    build.add_argument(
        "-o",
        "--output-dir",
        required=True,
        help="directory to write the generated site to",
    )
    build.add_argument(
        "--project",
        default="",
        help="project name shown in the generated site",
    )
    return parser


def _cmd_build(args: argparse.Namespace) -> int:
    input_format = plugins.input_formats.get(args.input_format)
    dataset = input_format.load(args.input_dir, {"project": args.project})
    generator = plugins.output_generators.get("html")
    generator.generate(dataset, Path(args.output_dir), {})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return 0
    try:
        if args.command == "build":
            return _cmd_build(args)
        raise AssertionError(f"unhandled command {args.command!r}")
    except UlvError as exc:
        print(f"ulv: error: {exc}", file=sys.stderr)
        return 1
