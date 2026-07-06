"""Command-line interface for Unladen Velocity."""

import argparse
import functools
import http.server
import sys
from pathlib import Path

from ulv import __version__, plugins
from ulv.config import load_settings
from ulv.errors import UlvError
from ulv.testbeds import load_testbeds_file


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
        description=(
            "Read benchmark results and generate a static HTML site. "
            "Every flag below can also be set in the config file "
            "(snake_case key); flags win over the file."
        ),
    )
    build.add_argument(
        "--config",
        metavar="FILE",
        help="config file (TOML, or JSON with a .json suffix); "
        "defaults to ./ulv.toml when present",
    )
    build.add_argument(
        "-i",
        "--input-format",
        help="input format name (e.g. 'asv')",
    )
    build.add_argument(
        "--input-dir",
        help="directory containing the benchmark result data",
    )
    build.add_argument(
        "-o",
        "--output-dir",
        help="directory to write the generated site to",
    )
    build.add_argument(
        "--project",
        help="project name shown in the generated site",
    )
    build.add_argument(
        "--project-url",
        help="URL the project name in the navbar links to",
    )
    build.add_argument(
        "--show-commit-url",
        help="URL prefix for commit links (commit hash is appended)",
    )
    build.add_argument(
        "--repo",
        help="path to the project's git repository, enabling commit "
        "ordering, dates, tags, and branch enrichment",
    )
    build.add_argument(
        "--branches",
        help="comma-separated branches to attribute results to "
        "(requires --repo; default: the repository's checked-out branch)",
    )
    build.add_argument(
        "--manifest",
        help="BMF sidecar manifest (JSON or TOML) mapping each input "
        "filename to its commit/date/branch/testbed metadata",
    )
    build.add_argument(
        "--filename-pattern",
        help="BMF filename template with {commit}/{date}/{branch}/"
        "{testbed} fields, e.g. '{commit}_{date}.json'",
    )
    build.add_argument(
        "--commit",
        help="commit hash for a single BMF input file",
    )
    build.add_argument(
        "--date",
        help="ISO 8601 date for a single BMF input file",
    )
    build.add_argument(
        "--branch",
        help="branch name for a single BMF input file",
    )
    build.add_argument(
        "--testbed",
        help="testbed name for a single BMF input file",
    )
    build.add_argument(
        "--testbeds-file",
        metavar="FILE",
        help="testbed decomposition file (TOML, or JSON with a .json "
        "suffix) with top-level 'factors' and 'map' — the same shape as "
        "the [testbeds] config table, which it overrides",
    )
    build.add_argument(
        "--allow-unmapped",
        action="store_true",
        default=None,
        help="include testbeds missing from the [testbeds] mapping with "
        "'unknown' factor values instead of failing",
    )

    serve = subparsers.add_parser(
        "serve",
        help="serve a built site locally for preview",
        description=(
            "Serve a previously built site directory over HTTP. "
            "A development convenience only; the generated site needs "
            "nothing beyond a static file server."
        ),
    )
    serve.add_argument(
        "directory",
        help="site directory to serve (output of 'ulv build')",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="host to bind (default: %(default)s)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port to bind; 0 picks a free port (default: %(default)s)",
    )
    return parser


def _cmd_build(args: argparse.Namespace) -> int:
    settings = load_settings(
        args.config,
        {
            "input_format": args.input_format,
            "input_dir": args.input_dir,
            "output_dir": args.output_dir,
            "project": args.project,
            "project_url": args.project_url,
            "show_commit_url": args.show_commit_url,
            "repo": args.repo,
            "branches": args.branches,
            "manifest": args.manifest,
            "filename_pattern": args.filename_pattern,
            "commit": args.commit,
            "date": args.date,
            "branch": args.branch,
            "testbed": args.testbed,
            "testbeds": (
                load_testbeds_file(args.testbeds_file) if args.testbeds_file else None
            ),
            "allow_unmapped": args.allow_unmapped,
        },
    )
    for key in ("input_format", "input_dir", "output_dir"):
        if getattr(settings, key) is None:
            flag = "--" + key.replace("_", "-")
            raise UlvError(
                f"missing required setting {key!r}: pass {flag} or set "
                f"{key!r} in the config file"
            )

    input_format = plugins.input_formats.get(settings.input_format)
    dataset = input_format.load(
        settings.input_dir,
        {
            "project": settings.project,
            "repo": settings.repo,
            "branches": settings.branch_list(),
            "manifest": settings.manifest,
            "filename_pattern": settings.filename_pattern,
            "commit": settings.commit,
            "date": settings.date,
            "branch": settings.branch,
            "testbed": settings.testbed,
            "testbeds": settings.testbeds,
            "allow_unmapped": settings.allow_unmapped,
        },
    )
    generator = plugins.output_generators.get("html")
    generator.generate(
        dataset,
        Path(settings.output_dir),
        {
            "project_url": settings.project_url,
            "show_commit_url": settings.show_commit_url,
        },
    )
    return 0


def serve_site(directory, host: str, port: int) -> http.server.ThreadingHTTPServer:
    """Bound (not yet running) HTTP server for a built site directory."""
    directory = Path(directory)
    if not directory.is_dir():
        raise UlvError(
            f"site directory not found: {directory}",
            offending_input=str(directory),
        )
    if not (directory / "index.html").is_file():
        raise UlvError(
            f"{directory} does not look like a built site (no index.html); "
            f"run 'ulv build' first",
            offending_input=str(directory),
        )
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )
    return http.server.ThreadingHTTPServer((host, port), handler)


def _cmd_serve(args: argparse.Namespace) -> int:
    with serve_site(args.directory, args.host, args.port) as server:
        host, port = server.server_address[:2]
        print(f"Serving {args.directory} at http://{host}:{port}/ (Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return 0
    try:
        if args.command == "build":
            return _cmd_build(args)
        if args.command == "serve":
            return _cmd_serve(args)
        raise AssertionError(f"unhandled command {args.command!r}")
    except UlvError as exc:
        print(f"ulv: error: {exc}", file=sys.stderr)
        return 1
