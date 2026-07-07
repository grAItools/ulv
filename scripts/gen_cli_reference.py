#!/usr/bin/env python3
"""Generate CLI reference documentation from argparse definitions.

Introspects the argparse parser defined in ulv.cli and produces a markdown
file suitable for inclusion in the user documentation.
"""

import argparse
from collections.abc import Iterator
from pathlib import Path

from ulv.cli import build_parser


def _format_option_row(action: argparse.Action) -> str:
    """Format a single option as a markdown table row."""
    # Build option string from option_strings
    opts = ", ".join(f"`{o}`" for o in action.option_strings) if action.option_strings else ""

    # Handle positional arguments
    if not action.option_strings:
        opts = f"`{action.dest}`"

    # Determine type
    if isinstance(action, argparse._StoreTrueAction):
        type_str = "flag"
    elif isinstance(action, argparse._StoreFalseAction):
        type_str = "flag"
    elif action.type is not None:
        type_str = action.type.__name__
    elif action.nargs == "?":
        type_str = "string"
    else:
        type_str = "string"

    # Determine default
    if action.default is None:
        default_str = ""
    elif action.default is argparse.SUPPRESS:
        default_str = ""
    elif isinstance(action.default, bool):
        default_str = f"`{str(action.default).lower()}`"
    elif action.default == "":
        default_str = '`""`'
    else:
        default_str = f"`{action.default}`"

    # Clean up help text
    help_text = action.help or ""
    # Replace %(prog)s and %(default)s placeholders
    help_text = help_text.replace("%(prog)s", "ulv")
    help_text = help_text.replace("%(default)s", str(action.default) if action.default is not None else "")

    return f"| {opts} | {type_str} | {default_str} | {help_text} |"


def _iter_options(parser: argparse.ArgumentParser) -> Iterator[argparse.Action]:
    """Yield non-help options from a parser."""
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._VersionAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        yield action


def generate_cli_reference() -> str:
    """Generate the CLI reference markdown content."""
    parser = build_parser()
    lines: list[str] = []

    # Header
    lines.append("# CLI Reference")
    lines.append("")
    lines.append("Complete reference for all ulv commands and options.")
    lines.append("")

    # Global usage
    lines.append("## Global options")
    lines.append("")
    lines.append("```")
    lines.append("ulv [-h] [--version] {build,serve} ...")
    lines.append("```")
    lines.append("")
    lines.append("| Option | Description |")
    lines.append("|--------|-------------|")
    lines.append("| `-h`, `--help` | Show help message and exit |")
    lines.append("| `--version` | Show program version and exit |")
    lines.append("")

    # Find subparsers
    subparsers_action = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers_action = action
            break

    if subparsers_action is None:
        return "\n".join(lines)

    # Process each subcommand
    for name, subparser in subparsers_action.choices.items():
        lines.append(f"## ulv {name}")
        lines.append("")
        lines.append(subparser.description or "")
        lines.append("")

        # Usage line
        usage_parts = [f"ulv {name} [-h]"]
        for action in _iter_options(subparser):
            if action.option_strings:
                opt = action.option_strings[-1]
                if action.metavar:
                    usage_parts.append(f"[{opt} {action.metavar}]")
                elif isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
                    usage_parts.append(f"[{opt}]")
                else:
                    usage_parts.append(f"[{opt} {action.dest.upper()}]")
            else:
                # Positional
                if action.nargs == "?":
                    usage_parts.append(f"[{action.dest}]")
                else:
                    usage_parts.append(action.dest)

        lines.append("```")
        lines.append(" ".join(usage_parts))
        lines.append("```")
        lines.append("")

        # Group options by category based on their position in the parser
        # For simplicity, we'll use help text patterns to categorize
        options = list(_iter_options(subparser))

        if name == "build":
            # Categorize build options
            general = []
            branding = []
            git_enrichment = []
            bmf_metadata = []
            testbed_decomp = []
            bencher_api = []

            for opt in options:
                dest = opt.dest

                if dest in ("config", "input_format", "input_dir", "output_dir"):
                    general.append(opt)
                elif dest in ("project", "project_url", "show_commit_url"):
                    branding.append(opt)
                elif dest in ("repo", "branches"):
                    git_enrichment.append(opt)
                elif dest in ("manifest", "filename_pattern", "commit", "date", "branch", "testbed"):
                    bmf_metadata.append(opt)
                elif dest in ("testbeds_file", "allow_unmapped"):
                    testbed_decomp.append(opt)
                elif dest.startswith("bencher"):
                    bencher_api.append(opt)
                else:
                    general.append(opt)

            def _write_section(title: str, opts: list) -> None:
                if not opts:
                    return
                lines.append(f"### {title}")
                lines.append("")
                lines.append("| Option | Type | Default | Description |")
                lines.append("|--------|------|---------|-------------|")
                # Add help row
                lines.append("| `-h`, `--help` | | | Show help message and exit |")
                for opt in opts:
                    lines.append(_format_option_row(opt))
                lines.append("")

            _write_section("General options", general)

            # Remove the duplicate help row for subsequent sections
            def _write_subsection(title: str, opts: list) -> None:
                if not opts:
                    return
                lines.append(f"### {title}")
                lines.append("")
                lines.append("| Option | Type | Default | Description |")
                lines.append("|--------|------|---------|-------------|")
                for opt in opts:
                    lines.append(_format_option_row(opt))
                lines.append("")

            _write_subsection("Site branding", branding)
            _write_subsection("Git enrichment (ASV)", git_enrichment)
            _write_subsection("BMF metadata", bmf_metadata)
            _write_subsection("Testbed decomposition", testbed_decomp)
            _write_subsection("Bencher API", bencher_api)

        else:
            # For serve and other commands, single table
            lines.append("| Option | Type | Default | Description |")
            lines.append("|--------|------|---------|-------------|")
            for opt in options:
                lines.append(_format_option_row(opt))
            lines.append("| `-h`, `--help` | | | Show help message and exit |")
            lines.append("")

    # Environment variables section
    lines.append("## Environment variables")
    lines.append("")
    lines.append("| Variable | Description |")
    lines.append("|----------|-------------|")
    lines.append("| `BENCHER_API_TOKEN` | Bencher API token (preferred over `--bencher-token`) |")
    lines.append("")

    # Examples section
    lines.append("## Examples")
    lines.append("")
    lines.append("Build from ASV results:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run ulv build -i asv --input-dir .asv/results -o site")
    lines.append("```")
    lines.append("")
    lines.append("Build from BMF with manifest:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run ulv build -i bmf --input-dir results -o site --manifest manifest.json")
    lines.append("```")
    lines.append("")
    lines.append("Build from Bencher cloud:")
    lines.append("")
    lines.append("```bash")
    lines.append("export BENCHER_API_TOKEN=\"your-token\"")
    lines.append("uv run ulv build -i bencher-api --bencher-project my-project -o site")
    lines.append("```")
    lines.append("")
    lines.append("Serve a built site:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run ulv serve site")
    lines.append("```")
    lines.append("")
    lines.append("Use a config file:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run ulv build --config myproject.toml")
    lines.append("```")
    lines.append("")

    # See also section
    lines.append("## See also")
    lines.append("")
    lines.append("- [Quickstart](quickstart.md) - Get started with ulv")
    lines.append("- [Configuration](config.md) - Config file format and options")
    lines.append("- [User Guide Index](index.md) - All documentation pages")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Write the CLI reference to docs/user/cli-reference.md."""
    content = generate_cli_reference()
    output_path = Path(__file__).parent.parent / "docs" / "user" / "cli-reference.md"
    output_path.write_text(content)
    print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
