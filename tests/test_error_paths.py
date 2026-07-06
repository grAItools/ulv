"""Table-driven error-path sweep (spec: malformed or unrecognized input
exits non-zero, names the offending input, and never emits a partially
broken site)."""

import json
import os
from pathlib import Path

import pytest

from ulv import plugins
from ulv.cli import main
from ulv.errors import UlvError
from ulv.inputs import bencher_api

ASV_FIXTURE = Path(__file__).parent / "fixtures" / "asv_results"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _asv_tree_with_bad_result(root: Path) -> Path:
    root.mkdir()
    _write(
        root / "benchmarks.json",
        json.dumps(
            {
                "time_x": {
                    "name": "time_x",
                    "param_names": [],
                    "params": [],
                    "type": "time",
                    "unit": "seconds",
                },
                "version": 2,
            }
        ),
    )
    _write(root / "box" / "machine.json", '{"machine": "box", "version": 1}')
    _write(root / "box" / "aaaaaaaa-py3.json", "{broken json")
    return root


def _bmf_tree(root: Path, content: str) -> Path:
    root.mkdir()
    _write(root / "snap.json", content)
    return root


def case_bad_asv_json(tmp_path):
    root = _asv_tree_with_bad_result(tmp_path / "results")
    return ["-i", "asv", "--input-dir", str(root)], "aaaaaaaa-py3.json"


def case_bad_bmf(tmp_path):
    root = _bmf_tree(tmp_path / "bmf", '["not", "an", "object"]')
    return ["-i", "bmf", "--input-dir", str(root)], "snap.json"


def case_bad_manifest(tmp_path):
    root = _bmf_tree(tmp_path / "bmf", '{"bench": {"latency": {"value": 1.0}}}')
    manifest = _write(root / "manifest.json", "{broken")
    return (
        ["-i", "bmf", "--input-dir", str(root), "--manifest", str(manifest)],
        "manifest.json",
    )


def case_bad_config(tmp_path):
    config = _write(tmp_path / "ulv.toml", "input_format = [broken")
    return ["--config", str(config)], "ulv.toml"


def case_uncovered_testbed(tmp_path):
    root = tmp_path / "bmf"
    root.mkdir()
    _write(root / "a.json", '{"bench": {"latency": {"value": 1.0}}}')
    _write(root / "b.json", '{"bench": {"latency": {"value": 2.0}}}')
    _write(
        root / "manifest.json",
        json.dumps(
            {
                "a.json": {
                    "commit": "a" * 8,
                    "date": "2026-01-01T00:00:00Z",
                    "testbed": "mapped-bed",
                },
                "b.json": {
                    "commit": "b" * 8,
                    "date": "2026-02-01T00:00:00Z",
                    "testbed": "forgotten-bed",
                },
            }
        ),
    )
    beds = _write(
        tmp_path / "beds.toml",
        'factors = ["os"]\n[map.mapped-bed]\nos = "linux"\n',
    )
    return (
        [
            "-i",
            "bmf",
            "--input-dir",
            str(root),
            "--manifest",
            str(root / "manifest.json"),
            "--testbeds-file",
            str(beds),
        ],
        "forgotten-bed",
    )


class _FailingTransport:
    def __init__(self, status=500, body=b"boom"):
        self.status = status
        self.body = body

    def get(self, url, headers):
        return self.status, self.body


def case_api_error(tmp_path, monkeypatch):
    plugin = plugins.input_formats.get("bencher-api")
    monkeypatch.setattr(plugin, "transport", _FailingTransport())
    return (
        ["-i", "bencher-api", "--bencher-project", "demo"],
        "/v0/projects/demo/reports",
    )


class _EndlessTransport:
    """Always returns a full page, ignoring pagination parameters."""

    def get(self, url, headers):
        return 200, json.dumps(
            [
                {
                    "uuid": "r",
                    "branch": {"name": "main", "head": {"version": {}}},
                    "testbed": {"name": "tb", "slug": "tb"},
                    "start_time": "2026-01-01T00:00:00Z",
                    "results": [],
                }
            ]
        ).encode()


def case_runaway_pagination(tmp_path, monkeypatch):
    monkeypatch.setattr(bencher_api, "PER_PAGE", 1)
    monkeypatch.setattr(bencher_api, "MAX_PAGES", 3)
    plugin = plugins.input_formats.get("bencher-api")
    monkeypatch.setattr(plugin, "transport", _EndlessTransport())
    return (
        ["-i", "bencher-api", "--bencher-project", "demo"],
        "pagination",
    )


CASES = [
    case_bad_asv_json,
    case_bad_bmf,
    case_bad_manifest,
    case_bad_config,
    case_uncovered_testbed,
    case_api_error,
    case_runaway_pagination,
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.__name__)
def test_error_named_and_no_partial_site(case, tmp_path, monkeypatch, capsys):
    if "monkeypatch" in case.__code__.co_varnames[: case.__code__.co_argcount]:
        argv_tail, needle = case(tmp_path, monkeypatch)
    else:
        argv_tail, needle = case(tmp_path)
    out_dir = tmp_path / "site"
    rc = main(["build", *argv_tail, "-o", str(out_dir)])
    assert rc != 0
    err = capsys.readouterr().err
    assert needle in err
    assert "Traceback" not in err
    assert not out_dir.exists()


@pytest.mark.parametrize("case", [case_bad_asv_json, case_bad_bmf], ids=["asv", "bmf"])
def test_previous_site_intact_on_failure(case, tmp_path, capsys):
    out_dir = tmp_path / "site"
    out_dir.mkdir()
    (out_dir / "index.html").write_text("previous site")
    argv_tail, _ = case(tmp_path)
    rc = main(["build", *argv_tail, "-o", str(out_dir)])
    assert rc != 0
    assert (out_dir / "index.html").read_text() == "previous site"


class TestNonUlvErrors:
    def test_unwritable_output_dir_is_a_clean_error(self, tmp_path, capsys):
        if os.geteuid() == 0:
            pytest.skip("root ignores directory permissions")
        parent = tmp_path / "ro"
        parent.mkdir()
        parent.chmod(0o500)
        try:
            rc = main(
                [
                    "build",
                    "-i",
                    "asv",
                    "--input-dir",
                    str(ASV_FIXTURE),
                    "-o",
                    str(parent / "nested" / "site"),
                ]
            )
        finally:
            parent.chmod(0o700)
        assert rc == 1
        err = capsys.readouterr().err
        assert "ulv: error" in err
        assert "Traceback" not in err


class TestBranchesRequireRepoEverywhere:
    def test_bmf_rejects_branches(self, tmp_path, capsys):
        root = _bmf_tree(tmp_path / "bmf", '{"bench": {"latency": {"value": 1.0}}}')
        rc = main(
            [
                "build",
                "-i",
                "bmf",
                "--input-dir",
                str(root),
                "--branches",
                "main",
                "-o",
                str(tmp_path / "site"),
            ]
        )
        assert rc == 1
        assert "branches" in capsys.readouterr().err

    def test_bencher_api_rejects_branches(self, tmp_path, capsys):
        rc = main(
            [
                "build",
                "-i",
                "bencher-api",
                "--bencher-project",
                "demo",
                "--branches",
                "main",
                "-o",
                str(tmp_path / "site"),
            ]
        )
        assert rc == 1
        assert "branches" in capsys.readouterr().err

    def test_bencher_api_rejects_repo(self, tmp_path):
        from ulv.inputs.bencher_api import BencherApiInputFormat

        with pytest.raises(UlvError, match="repo"):
            BencherApiInputFormat().load(
                None, {"bencher_project": "demo", "repo": str(tmp_path)}
            )
