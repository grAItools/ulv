"""Tests for the `ulv` CLI entry point (src/ulv/cli.py)."""

import importlib.metadata

import pytest

from ulv.cli import main


def test_help_exits_zero_and_prints_usage(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()
    assert "ulv" in out


def test_version_prints_package_version(capsys):
    expected = importlib.metadata.version("unladen-velocity")
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert expected in capsys.readouterr().out


def test_bogus_flag_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--definitely-not-a-flag"])
    assert excinfo.value.code != 0
    assert "usage" in capsys.readouterr().err.lower()


def test_no_arguments_returns_zero():
    assert main([]) == 0
