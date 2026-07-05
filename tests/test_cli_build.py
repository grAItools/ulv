"""Tests for `ulv build` (src/ulv/cli.py)."""

import json
from pathlib import Path

from ulv.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "asv_results"


def test_build_generates_site(tmp_path):
    out_dir = tmp_path / "site"
    rc = main(
        [
            "build",
            "--input-format",
            "asv",
            "--input-dir",
            str(FIXTURE),
            "--output-dir",
            str(out_dir),
            "--project",
            "demo",
        ]
    )
    assert rc == 0
    assert (out_dir / "index.html").is_file()
    index = json.loads((out_dir / "index.json").read_text())
    assert index["project"] == "demo"


def test_short_flags(tmp_path):
    out_dir = tmp_path / "site"
    rc = main(["build", "-i", "asv", "--input-dir", str(FIXTURE), "-o", str(out_dir)])
    assert rc == 0
    assert (out_dir / "index.html").is_file()


def test_missing_input_dir_fails_without_output(tmp_path, capsys):
    out_dir = tmp_path / "site"
    rc = main(
        [
            "build",
            "-i",
            "asv",
            "--input-dir",
            str(tmp_path / "does-not-exist"),
            "-o",
            str(out_dir),
        ]
    )
    assert rc == 1
    assert "does-not-exist" in capsys.readouterr().err
    assert not out_dir.exists()


def test_unknown_input_format_fails(tmp_path, capsys):
    rc = main(
        [
            "build",
            "-i",
            "nope",
            "--input-dir",
            str(FIXTURE),
            "-o",
            str(tmp_path / "site"),
        ]
    )
    assert rc == 1
    assert "nope" in capsys.readouterr().err
