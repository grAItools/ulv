#!/usr/bin/env python3
"""Check if documentation is up to date with source code.

Regenerates the CLI reference to a temporary location and compares it to the
current file. Exits with code 0 if identical, 1 if stale.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _import_cli_reference_generator():
    """Import generate_cli_reference from sibling module."""
    scripts_dir = Path(__file__).parent
    sys.path.insert(0, str(scripts_dir))
    from gen_cli_reference import generate_cli_reference

    return generate_cli_reference


def main() -> int:
    """Check if the CLI reference is up to date."""
    cli_ref_path = Path(__file__).parent.parent / "docs" / "user" / "cli-reference.md"

    # Import and generate the expected content
    generate_cli_reference = _import_cli_reference_generator()
    expected = generate_cli_reference()

    # Read the current content
    if not cli_ref_path.exists():
        print(f"docs-check: {cli_ref_path} does not exist")
        return 1

    current = cli_ref_path.read_text()

    # Compare
    if current == expected:
        print("docs-check: CLI reference is up to date")
        return 0
    else:
        print("docs-check: CLI reference is stale; run 'make docs' to regenerate")
        return 1


if __name__ == "__main__":
    sys.exit(main())
