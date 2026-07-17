"""Extract a release's section body from CHANGELOG.md.

Usage: python scripts/release_notes.py <version>

Prints the body of the `## [<version>]` section (Keep a Changelog format)
to stdout. Exits 1 if no such section exists, so a release cannot be cut
with empty notes.
"""

import re
import sys
from pathlib import Path


def extract_release_notes(changelog: str, version: str) -> str | None:
    """Return the body under `## [<version>]`, or None if absent.

    The section runs from its header to the next `## ` heading. Trailing
    link-reference lines (``[x]: https://...``) are dropped.
    """
    header = re.compile(rf"^## \[{re.escape(version)}\]")
    lines = changelog.splitlines()
    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        return None

    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if re.match(r"^\[[^\]]+\]:\s", line):
            continue
        body.append(line)

    text = "\n".join(body).strip()
    return text or None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_notes.py <version>", file=sys.stderr)
        return 2
    version = argv[1]
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    notes = extract_release_notes(changelog, version)
    if notes is None:
        print(
            f"error: no CHANGELOG.md section '## [{version}]' — "
            "promote [Unreleased] before tagging",
            file=sys.stderr,
        )
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
