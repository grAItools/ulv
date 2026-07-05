"""Tests for the BMF input plugin (src/ulv/inputs/bmf.py).

Ordering comes from explicit sidecar metadata only (spec Decision 3):
files are written and mtime-touched in misleading orders to prove
neither file order, name order, nor mtime ever leaks into the series.
"""

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from ulv import plugins
from ulv.errors import UlvError
from ulv.inputs.bmf import BmfInputFormat

BMF_ONE = {
    "adapter::json": {
        "latency": {"value": 3.5, "lower_value": 3.1, "upper_value": 4.0},
        "throughput": {"value": 100.0},
    },
    "parser": {
        "latency": {"value": 7.0},
    },
}

BMF_TWO = {
    "adapter::json": {
        "latency": {"value": 3.0, "lower_value": 2.9, "upper_value": 3.2},
        "throughput": {"value": 110.0},
    },
    "parser": {
        "latency": {"value": 6.5},
    },
}

BMF_THREE = {
    "adapter::json": {
        "latency": {"value": 2.8},
    },
}


def _write(path: Path, data) -> Path:
    path.write_text(json.dumps(data))
    return path


def _manifest(root: Path, entries: dict, fmt: str = "json") -> Path:
    if fmt == "json":
        return _write(root / "manifest.json", entries)
    lines = []
    for filename, meta in entries.items():
        lines.append(f'["{filename}"]')
        for key, value in meta.items():
            lines.append(f'{key} = "{value}"')
        lines.append("")
    path = root / "manifest.toml"
    path.write_text("\n".join(lines))
    return path


@pytest.fixture
def history_dir(tmp_path):
    """Three snapshots whose name order, write order, and mtime order all
    DISAGREE with the metadata date order (c -> a -> b)."""
    root = tmp_path / "bmf"
    root.mkdir()
    _write(root / "b.json", BMF_THREE)
    _write(root / "a.json", BMF_TWO)
    _write(root / "c.json", BMF_ONE)
    # mtimes: newest file (by metadata) gets the oldest mtime.
    os.utime(root / "c.json", (2_000_000_000, 2_000_000_000))
    os.utime(root / "a.json", (1_500_000_000, 1_500_000_000))
    os.utime(root / "b.json", (1_000_000_000, 1_000_000_000))
    manifest = _manifest(
        root,
        {
            "a.json": {"commit": "a" * 8, "date": "2026-02-01T00:00:00Z"},
            "b.json": {"commit": "b" * 8, "date": "2026-03-01T00:00:00Z"},
            "c.json": {"commit": "c" * 8, "date": "2026-01-01T00:00:00Z"},
        },
    )
    return root, manifest


def _load(source, **options):
    return BmfInputFormat().load(source, {"project": "demo", **options})


class TestParsing:
    def test_each_benchmark_measure_pair_is_one_benchmark(self, tmp_path):
        source = _write(tmp_path / "snap.json", BMF_ONE)
        dataset = _load(source)
        assert set(dataset.benchmarks) == {
            "adapter::json (latency)",
            "adapter::json (throughput)",
            "parser (latency)",
        }
        assert dataset.benchmarks["adapter::json (latency)"].unit == "latency"
        assert dataset.benchmarks["adapter::json (throughput)"].unit == "throughput"

    def test_values_and_bounds_preserved(self, tmp_path):
        source = _write(tmp_path / "snap.json", BMF_ONE)
        dataset = _load(source)
        (series,) = dataset.series_for("adapter::json (latency)")
        (point,) = series.points.values()
        assert point.value == 3.5
        assert point.lower == 3.1
        assert point.upper == 4.0

    def test_absent_bounds_stay_none_not_zero(self, tmp_path):
        source = _write(tmp_path / "snap.json", BMF_ONE)
        dataset = _load(source)
        (series,) = dataset.series_for("adapter::json (throughput)")
        (point,) = series.points.values()
        assert point.lower is None
        assert point.upper is None

    def test_registered_as_builtin(self):
        assert isinstance(plugins.input_formats.get("bmf"), BmfInputFormat)


class TestSnapshot:
    def test_single_file_without_metadata_is_snapshot(self, tmp_path):
        source = _write(tmp_path / "snap.json", BMF_ONE)
        dataset = _load(source)
        assert dataset.has_time_axis is False
        assert len(dataset.revisions) == 1

    def test_single_file_flags_recorded(self, tmp_path):
        source = _write(tmp_path / "snap.json", BMF_ONE)
        dataset = _load(
            source,
            commit="abc12345",
            date="2026-01-02T03:04:05+02:00",
            branch="main",
            testbed="linux-x64",
        )
        (revision,) = dataset.revisions
        assert revision.commit_hash == "abc12345"
        assert revision.branch == "main"
        assert revision.date == dt.datetime(2026, 1, 2, 1, 4, 5, tzinfo=dt.UTC)
        (environment,) = dataset.environments
        assert environment.factors == {"testbed": "linux-x64"}


class TestManifestOrdering:
    def test_series_order_follows_manifest_not_files(self, history_dir):
        root, manifest = history_dir
        dataset = _load(root, manifest=str(manifest))
        assert [r.commit_hash for r in dataset.revisions] == [
            "c" * 8,
            "a" * 8,
            "b" * 8,
        ]
        (series,) = dataset.series_for("adapter::json (latency)")
        ordered = [series.points[r.id].value for r in dataset.revisions]
        assert ordered == [3.5, 3.0, 2.8]

    def test_toml_manifest_equivalent(self, history_dir):
        root, json_manifest = history_dir
        # Only the configured manifest is excluded from data collection,
        # so the unused JSON manifest must not linger in the data dir.
        json_manifest.unlink()
        manifest = _manifest(
            root,
            {
                "a.json": {"commit": "a" * 8, "date": "2026-02-01T00:00:00Z"},
                "b.json": {"commit": "b" * 8, "date": "2026-03-01T00:00:00Z"},
                "c.json": {"commit": "c" * 8, "date": "2026-01-01T00:00:00Z"},
            },
            fmt="toml",
        )
        dataset = _load(root, manifest=str(manifest))
        assert [r.commit_hash for r in dataset.revisions] == [
            "c" * 8,
            "a" * 8,
            "b" * 8,
        ]

    def test_file_missing_from_manifest_named(self, history_dir):
        root, _ = history_dir
        manifest = _manifest(
            root,
            {
                "a.json": {"commit": "a" * 8, "date": "2026-02-01T00:00:00Z"},
                "b.json": {"commit": "b" * 8, "date": "2026-03-01T00:00:00Z"},
            },
        )
        with pytest.raises(UlvError, match="c.json"):
            _load(root, manifest=str(manifest))

    def test_manifest_entry_without_file_named(self, history_dir):
        root, _ = history_dir
        manifest = _manifest(
            root,
            {
                "a.json": {"commit": "a" * 8, "date": "2026-02-01T00:00:00Z"},
                "b.json": {"commit": "b" * 8, "date": "2026-03-01T00:00:00Z"},
                "c.json": {"commit": "c" * 8, "date": "2026-01-01T00:00:00Z"},
                "ghost.json": {"commit": "d" * 8, "date": "2026-04-01T00:00:00Z"},
            },
        )
        with pytest.raises(UlvError, match="ghost.json"):
            _load(root, manifest=str(manifest))

    def test_branch_and_testbed_from_manifest(self, tmp_path):
        root = tmp_path / "bmf"
        root.mkdir()
        _write(root / "a.json", BMF_ONE)
        _write(root / "b.json", BMF_TWO)
        manifest = _manifest(
            root,
            {
                "a.json": {
                    "commit": "a" * 8,
                    "date": "2026-01-01T00:00:00Z",
                    "branch": "main",
                    "testbed": "linux-x64",
                },
                "b.json": {
                    "commit": "b" * 8,
                    "date": "2026-02-01T00:00:00Z",
                    "branch": "main",
                    "testbed": "macos-arm",
                },
            },
        )
        dataset = _load(root, manifest=str(manifest))
        assert [r.branch for r in dataset.revisions] == ["main", "main"]
        assert sorted(e.id for e in dataset.environments) == [
            "linux-x64",
            "macos-arm",
        ]
        assert dataset.environment_axes()["testbed"] == ("linux-x64", "macos-arm")


class TestFilenamePattern:
    def test_pattern_extracts_commit_and_date(self, tmp_path):
        root = tmp_path / "bmf"
        root.mkdir()
        _write(root / "bbbbbbbb_2026-03-01.json", BMF_THREE)
        _write(root / "aaaaaaaa_2026-02-01.json", BMF_TWO)
        _write(root / "cccccccc_2026-01-01.json", BMF_ONE)
        dataset = _load(root, filename_pattern="{commit}_{date}.json")
        assert [r.commit_hash for r in dataset.revisions] == [
            "cccccccc",
            "aaaaaaaa",
            "bbbbbbbb",
        ]

    def test_non_matching_filename_named(self, tmp_path):
        root = tmp_path / "bmf"
        root.mkdir()
        _write(root / "aaaaaaaa_2026-02-01.json", BMF_TWO)
        _write(root / "odd-name.json", BMF_ONE)
        with pytest.raises(UlvError, match="odd-name.json"):
            _load(root, filename_pattern="{commit}_{date}.json")

    def test_unknown_pattern_field_rejected(self, tmp_path):
        root = tmp_path / "bmf"
        root.mkdir()
        _write(root / "a.json", BMF_ONE)
        with pytest.raises(UlvError, match="flavour"):
            _load(root, filename_pattern="{flavour}.json")


class TestMetadataErrors:
    def test_multi_file_without_any_metadata_named(self, tmp_path):
        root = tmp_path / "bmf"
        root.mkdir()
        _write(root / "a.json", BMF_ONE)
        _write(root / "b.json", BMF_TWO)
        with pytest.raises(UlvError, match="a.json"):
            _load(root)

    def test_single_file_flags_rejected_for_multi_file(self, tmp_path):
        root = tmp_path / "bmf"
        root.mkdir()
        _write(root / "a.json", BMF_ONE)
        _write(root / "b.json", BMF_TWO)
        with pytest.raises(UlvError, match="commit"):
            _load(root, commit="abc", date="2026-01-01")

    def test_naive_date_treated_as_utc(self, tmp_path):
        source = _write(tmp_path / "snap.json", BMF_ONE)
        dataset = _load(source, commit="abc", date="2026-01-02T03:04:05")
        (revision,) = dataset.revisions
        assert revision.date == dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC)

    def test_bad_date_named(self, tmp_path):
        source = _write(tmp_path / "snap.json", BMF_ONE)
        with pytest.raises(UlvError, match="not-a-date"):
            _load(source, commit="abc", date="not-a-date")


class TestMalformedBmf:
    def test_top_level_not_object_named(self, tmp_path):
        source = _write(tmp_path / "bad.json", ["nope"])
        with pytest.raises(UlvError, match="bad.json"):
            _load(source)

    def test_measures_not_object_names_benchmark(self, tmp_path):
        source = _write(tmp_path / "bad.json", {"bench": 42})
        with pytest.raises(UlvError, match="bench") as excinfo:
            _load(source)
        assert "bad.json" in str(excinfo.value)

    def test_metric_not_object_names_measure(self, tmp_path):
        source = _write(tmp_path / "bad.json", {"bench": {"latency": "fast"}})
        with pytest.raises(UlvError, match="latency"):
            _load(source)

    def test_non_numeric_value_named(self, tmp_path):
        source = _write(
            tmp_path / "bad.json", {"bench": {"latency": {"value": "fast"}}}
        )
        with pytest.raises(UlvError, match="latency"):
            _load(source)

    def test_missing_value_key_named(self, tmp_path):
        source = _write(
            tmp_path / "bad.json", {"bench": {"latency": {"lower_value": 1.0}}}
        )
        with pytest.raises(UlvError, match="latency"):
            _load(source)

    def test_missing_source_named(self, tmp_path):
        with pytest.raises(UlvError, match="absent"):
            _load(tmp_path / "absent")

    def test_empty_directory_named(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        with pytest.raises(UlvError, match="empty"):
            _load(root)
