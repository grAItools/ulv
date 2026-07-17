"""Tests for scripts/release_notes.py — the CHANGELOG slicer the release
workflow uses to build release notes and to fail loudly on a missing section.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCRIPT = REPO_ROOT / "scripts" / "release_notes.py"


def _load():
    spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_notes = _load()

SAMPLE = """# Changelog

## [Unreleased]

## [1.2.0] — 2026-08-01

### Added

- Thing one.
- Thing two.

## [1.1.0] — 2026-07-01

### Fixed

- Old bug.

[Unreleased]: https://example/compare/v1.2.0...HEAD
[1.2.0]: https://example/releases/tag/v1.2.0
[1.1.0]: https://example/releases/tag/v1.1.0
"""


def test_extracts_matching_section_and_stops_at_next():
    notes = release_notes.extract_release_notes(SAMPLE, "1.2.0")
    assert "Thing one." in notes
    assert "Thing two." in notes
    assert "Old bug." not in notes


def test_drops_trailing_link_references():
    # 1.1.0 is the last version section, so the link-reference block follows
    # it directly and must be filtered out.
    notes = release_notes.extract_release_notes(SAMPLE, "1.1.0")
    assert "Old bug." in notes
    assert "https://example" not in notes


def test_missing_section_returns_none():
    assert release_notes.extract_release_notes(SAMPLE, "9.9.9") is None


def test_empty_section_returns_none():
    # [Unreleased] has no body before the next heading.
    assert release_notes.extract_release_notes(SAMPLE, "Unreleased") is None
