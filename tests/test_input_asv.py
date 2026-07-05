"""Tests for the ASV input plugin (src/ulv/inputs/asv.py).

The fixture under tests/fixtures/asv_results/ is api_version 2 data
derived from external/asv/test/example_results (real commit hashes,
dates, and env params); spot-checks below compare loaded values against
the raw fixture JSON rather than hardcoded copies.
"""

import json
import math
from pathlib import Path

import pytest

from ulv import plugins
from ulv.errors import UlvError
from ulv.inputs.asv import AsvInputFormat

FIXTURE = Path(__file__).parent / "fixtures" / "asv_results"

COMMIT_OLD = "05d4f83d436ce55054016c24b31d959a85b44a1c"
COMMIT_MID = "fcf8c079fae7ebad9f27bd31a819f0e4fdd85b99"
COMMIT_NEW = "05d283b9694ed6db6e3f2df3f21d832e78bded7f"

ENV_C18 = "cheetah/py2.7-Cython-numpy1.8"
ENV_C19 = "cheetah/py2.7-Cython-numpy1.9"
ENV_L18 = "leopard/py2.7-Cython-numpy1.8"


@pytest.fixture(scope="module")
def dataset():
    return AsvInputFormat().load(FIXTURE, {"project": "demo"})


def _raw(machine: str, filename: str) -> dict:
    return json.loads((FIXTURE / machine / filename).read_text())


def _point(dataset, benchmark, environment, revision):
    (series,) = [
        s for s in dataset.series_for(benchmark) if s.environment == environment
    ]
    return series.points[revision]


class TestRevisionOrdering:
    def test_revisions_sorted_by_result_date_not_filename(self, dataset):
        assert [r.id for r in dataset.revisions] == [
            COMMIT_OLD,
            COMMIT_MID,
            COMMIT_NEW,
        ]

    def test_revision_carries_commit_hash_and_date(self, dataset):
        raw = _raw("cheetah", "fcf8c079-py2.7-Cython-numpy1.8.json")
        revision = dataset.revisions[1]
        assert revision.commit_hash == raw["commit_hash"]
        assert revision.date is not None
        assert revision.date.timestamp() * 1000 == raw["date"]


class TestValues:
    def test_scalar_value_matches_raw_json(self, dataset):
        raw = _raw("cheetah", "fcf8c079-py2.7-Cython-numpy1.8.json")
        raw_value = raw["results"]["time_units.time_unit_parse"][0][0]
        point = _point(dataset, "time_units.time_unit_parse", ENV_C18, COMMIT_MID)
        assert point.value == raw_value

    def test_parameterized_values_match_raw_json(self, dataset):
        raw = _raw("cheetah", "fcf8c079-py2.7-Cython-numpy1.8.json")
        raw_values = raw["results"]["params_examples.mem_param"][0]
        point = _point(dataset, "params_examples.mem_param", ENV_C18, COMMIT_MID)
        assert list(point.value) == raw_values

    def test_partial_failure_keeps_null_slot(self, dataset):
        point = _point(
            dataset, "params_examples.ParamSuite.track_value", ENV_C18, COMMIT_MID
        )
        assert list(point.value) == [1, 4, None]

    def test_collapsed_all_failed_result_expands_to_nones(self, dataset):
        point = _point(
            dataset, "params_examples.ParamSuite.track_value", ENV_C18, COMMIT_NEW
        )
        assert list(point.value) == [None, None, None]

    def test_nan_means_skipped_and_survives_load(self, dataset):
        point = _point(dataset, "time_ci_small", ENV_C18, COMMIT_NEW)
        assert math.isnan(point.value)

    def test_stats_reassembled_from_columns(self, dataset):
        point = _point(dataset, "time_ci_small", ENV_C18, COMMIT_MID)
        assert point.stats == {
            "ci_99_a": 3.1,
            "ci_99_b": 3.9,
            "q_25": 3.0,
            "q_75": 3.0,
            "number": 1,
            "repeat": 2,
        }

    def test_unconsumed_row_fields_preserved_in_extra(self, dataset):
        point = _point(dataset, "time_units.time_unit_parse", ENV_C18, COMMIT_MID)
        assert point.extra["duration"] == 1.5


class TestBenchmarks:
    def test_param_decomposition_matches_benchmarks_json(self, dataset):
        raw = json.loads((FIXTURE / "benchmarks.json").read_text())
        entry = raw["params_examples.mem_param"]
        benchmark = dataset.benchmarks["params_examples.mem_param"]
        assert list(benchmark.param_names) == entry["param_names"]
        assert [list(axis) for axis in benchmark.params] == entry["params"]
        assert benchmark.unit == entry["unit"]
        assert benchmark.type == entry["type"]

    def test_unconsumed_benchmark_fields_preserved_in_extra(self, dataset):
        raw = json.loads((FIXTURE / "benchmarks.json").read_text())
        benchmark = dataset.benchmarks["time_units.time_unit_parse"]
        assert benchmark.extra["code"] == raw["time_units.time_unit_parse"]["code"]
        assert (
            benchmark.extra["timeout"] == raw["time_units.time_unit_parse"]["timeout"]
        )


class TestEnvironments:
    def test_multi_machine_environments_are_distinct(self, dataset):
        assert sorted(e.id for e in dataset.environments) == [
            ENV_C18,
            ENV_C19,
            ENV_L18,
        ]

    def test_machine_axis_spans_both_machines(self, dataset):
        axes = dataset.environment_axes()
        assert axes["machine"] == ("cheetah", "leopard")
        assert axes["numpy"] == ("1.8", "1.9")

    def test_env_vars_become_env_prefixed_factors(self, dataset):
        (env,) = [e for e in dataset.environments if e.id == ENV_C19]
        assert env.factors["env-ULV_TEST"] == "1"

    def test_null_env_param_coerced_to_empty_string(self, dataset):
        (env,) = [e for e in dataset.environments if e.id == ENV_C19]
        assert env.factors["lapack"] == ""

    def test_machine_info_preserved_without_num_cpu(self, dataset):
        (env,) = [e for e in dataset.environments if e.id == ENV_C18]
        info = env.extra["machine_info"]
        assert info["os"] == "Linux (Fedora 20)"
        assert "num_cpu" not in info

    def test_file_level_durations_preserved(self, dataset):
        (env,) = [e for e in dataset.environments if e.id == ENV_C18]
        assert env.extra["durations"][COMMIT_MID] == {"<build>": 32.565}


class TestProjectAndRegistration:
    def test_project_taken_from_options(self, dataset):
        assert dataset.project == "demo"

    def test_registered_as_builtin_input_format(self):
        assert isinstance(plugins.input_formats.get("asv"), AsvInputFormat)


def _write_minimal_tree(
    root: Path,
    *,
    benchmarks: dict | None = None,
    machine: dict | None = None,
    result: dict | None = None,
) -> Path:
    """A one-machine, one-result tree; pass overrides to break pieces of it."""
    if benchmarks is None:
        benchmarks = {
            "time_x": {
                "name": "time_x",
                "param_names": [],
                "params": [],
                "type": "time",
                "unit": "seconds",
            },
            "version": 2,
        }
    if machine is None:
        machine = {"machine": "box", "os": "Linux", "version": 1}
    if result is None:
        result = {
            "commit_hash": "a" * 40,
            "date": 1356631584000,
            "env_name": "py3",
            "env_vars": {},
            "params": {"machine": "box", "python": "3.11"},
            "python": "3.11",
            "requirements": {},
            "result_columns": ["result", "params"],
            "results": {"time_x": [[1.0], []]},
            "durations": {},
            "version": 2,
        }
    (root / "benchmarks.json").write_text(json.dumps(benchmarks))
    machine_dir = root / "box"
    machine_dir.mkdir()
    (machine_dir / "machine.json").write_text(json.dumps(machine))
    (machine_dir / "aaaaaaaa-py3.json").write_text(json.dumps(result))
    return root


class TestMalformedInput:
    def test_missing_source_directory(self, tmp_path):
        with pytest.raises(UlvError, match="no-such-dir"):
            AsvInputFormat().load(tmp_path / "no-such-dir", {})

    def test_missing_benchmarks_json_named(self, tmp_path):
        _write_minimal_tree(tmp_path)
        (tmp_path / "benchmarks.json").unlink()
        with pytest.raises(UlvError, match="benchmarks.json"):
            AsvInputFormat().load(tmp_path, {})

    def test_bad_json_result_file_named(self, tmp_path):
        _write_minimal_tree(tmp_path)
        (tmp_path / "box" / "aaaaaaaa-py3.json").write_text("{not json")
        with pytest.raises(UlvError, match="aaaaaaaa-py3.json"):
            AsvInputFormat().load(tmp_path, {})

    def test_result_dir_without_machine_json_named(self, tmp_path):
        _write_minimal_tree(tmp_path)
        (tmp_path / "box" / "machine.json").unlink()
        with pytest.raises(UlvError, match="machine.json"):
            AsvInputFormat().load(tmp_path, {})

    def test_machine_json_without_machine_key_named(self, tmp_path):
        _write_minimal_tree(tmp_path, machine={"os": "Linux", "version": 1})
        with pytest.raises(UlvError, match="machine.json"):
            AsvInputFormat().load(tmp_path, {})

    def test_api_version_1_result_file_advises_asv_update(self, tmp_path):
        _write_minimal_tree(tmp_path)
        v1 = {
            "commit_hash": "a" * 40,
            "date": 1356631584000,
            "params": {"machine": "box", "python": "3.11"},
            "python": "3.11",
            "requirements": {},
            "results": {"time_x": 1.0},
            "version": 1,
        }
        (tmp_path / "box" / "aaaaaaaa-py3.json").write_text(json.dumps(v1))
        with pytest.raises(UlvError, match="aaaaaaaa-py3.json") as excinfo:
            AsvInputFormat().load(tmp_path, {})
        assert "api_version 1" in str(excinfo.value)
        assert "asv update" in str(excinfo.value)

    def test_wrong_benchmarks_json_version_named(self, tmp_path):
        _write_minimal_tree(tmp_path)
        (tmp_path / "benchmarks.json").write_text(json.dumps({"version": 1}))
        with pytest.raises(UlvError, match="benchmarks.json"):
            AsvInputFormat().load(tmp_path, {})

    def test_missing_result_key_named(self, tmp_path):
        _write_minimal_tree(tmp_path)
        broken = json.loads((tmp_path / "box" / "aaaaaaaa-py3.json").read_text())
        del broken["commit_hash"]
        (tmp_path / "box" / "aaaaaaaa-py3.json").write_text(json.dumps(broken))
        with pytest.raises(UlvError, match="aaaaaaaa-py3.json"):
            AsvInputFormat().load(tmp_path, {})


def _benchmarks_entry(name, *, params=(), param_names=(), version=None):
    entry = {
        "name": name,
        "param_names": list(param_names),
        "params": [list(axis) for axis in params],
        "type": "time",
        "unit": "seconds",
    }
    if version is not None:
        entry["version"] = version
    return entry


def _result_file(
    results,
    *,
    commit="a" * 40,
    date=1356631584000,
    env_name="py3",
    params=None,
    requirements=None,
    columns=("result", "params"),
):
    return {
        "commit_hash": commit,
        "date": date,
        "env_name": env_name,
        "env_vars": {},
        "params": params or {"machine": "box", "python": "3.11"},
        "python": "3.11",
        "requirements": requirements or {},
        "result_columns": list(columns),
        "results": results,
        "durations": {},
        "version": 2,
    }


class TestVersionMismatch:
    def test_result_with_mismatched_benchmark_version_excluded(self, tmp_path):
        benchmarks = {
            "time_x": _benchmarks_entry("time_x", version="expected"),
            "version": 2,
        }
        result = _result_file(
            {"time_x": [[1.0], [], "stale"]},
            columns=("result", "params", "version"),
        )
        _write_minimal_tree(tmp_path, benchmarks=benchmarks, result=result)
        dataset = AsvInputFormat().load(tmp_path, {})
        assert dataset.series_for("time_x") == ()

    def test_stored_version_without_benchmarks_version_excluded(self, tmp_path):
        # ASV excludes whenever the stored version differs from the (possibly
        # absent) benchmarks.json version — see asv/results.py:308-316.
        benchmarks = {"time_x": _benchmarks_entry("time_x"), "version": 2}
        result = _result_file(
            {"time_x": [[1.0], [], "stale"]},
            columns=("result", "params", "version"),
        )
        _write_minimal_tree(tmp_path, benchmarks=benchmarks, result=result)
        dataset = AsvInputFormat().load(tmp_path, {})
        assert dataset.series_for("time_x") == ()

    def test_result_without_stored_version_included(self, tmp_path):
        benchmarks = {
            "time_x": _benchmarks_entry("time_x", version="expected"),
            "version": 2,
        }
        result = _result_file({"time_x": [[1.0], []]})
        _write_minimal_tree(tmp_path, benchmarks=benchmarks, result=result)
        dataset = AsvInputFormat().load(tmp_path, {})
        assert len(dataset.series_for("time_x")) == 1


class TestParamRemapping:
    def test_scalar_result_for_now_parameterized_benchmark_is_all_none(self, tmp_path):
        benchmarks = {
            "time_x": _benchmarks_entry(
                "time_x", params=[["1", "2"]], param_names=["n"]
            ),
            "version": 2,
        }
        result = _result_file({"time_x": [[1.0], []]})
        _write_minimal_tree(tmp_path, benchmarks=benchmarks, result=result)
        dataset = AsvInputFormat().load(tmp_path, {})
        (series,) = dataset.series_for("time_x")
        assert list(series.points["a" * 40].value) == [None, None]

    def test_remap_keeps_stats_and_samples_aligned(self, tmp_path):
        benchmarks = {
            "time_x": _benchmarks_entry(
                "time_x", params=[["1", "2"]], param_names=["n"]
            ),
            "version": 2,
        }
        # Stored with the parameter axis reversed relative to benchmarks.json.
        result = _result_file(
            {
                "time_x": [
                    [20.0, 10.0],
                    [["2", "1"]],
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    [2, 1],
                    None,
                    [[20.5], [10.5]],
                ]
            },
            columns=(
                "result",
                "params",
                "version",
                "started_at",
                "duration",
                "stats_ci_99_a",
                "stats_ci_99_b",
                "stats_q_25",
                "stats_q_75",
                "stats_number",
                "stats_repeat",
                "samples",
            ),
        )
        _write_minimal_tree(tmp_path, benchmarks=benchmarks, result=result)
        dataset = AsvInputFormat().load(tmp_path, {})
        (series,) = dataset.series_for("time_x")
        point = series.points["a" * 40]
        assert list(point.value) == [10.0, 20.0]
        assert point.stats == ({"number": 1}, {"number": 2})
        assert point.extra["samples"] == [[10.5], [20.5]]


class TestFactorMerging:
    def test_factors_merged_across_result_files_of_same_env(self, tmp_path):
        _write_minimal_tree(tmp_path)
        second = _result_file(
            {"time_x": [[2.0], []]},
            commit="b" * 40,
            date=1356631585000,
            params={"machine": "box", "python": "3.11", "blas": "openblas"},
        )
        (tmp_path / "box" / "bbbbbbbb-py3.json").write_text(json.dumps(second))
        dataset = AsvInputFormat().load(tmp_path, {})
        (env,) = dataset.environments
        assert env.factors["blas"] == "openblas"
        assert env.factors["python"] == "3.11"

    def test_conflicting_factor_value_names_the_file(self, tmp_path):
        _write_minimal_tree(tmp_path)
        second = _result_file(
            {"time_x": [[2.0], []]},
            commit="b" * 40,
            date=1356631585000,
            params={"machine": "box", "python": "3.12"},
        )
        (tmp_path / "box" / "bbbbbbbb-py3.json").write_text(json.dumps(second))
        with pytest.raises(UlvError, match="bbbbbbbb-py3.json") as excinfo:
            AsvInputFormat().load(tmp_path, {})
        assert "python" in str(excinfo.value)


class TestEnvironmentExtras:
    def test_python_and_requirements_preserved(self, dataset):
        (env,) = [e for e in dataset.environments if e.id == ENV_C18]
        assert env.extra["python"] == "2.7"
        # Cython appears only in this file's requirements, not in its params.
        raw = _raw("cheetah", "05d283b9-py2.7-Cython-numpy1.8.json")
        assert "Cython" in raw["requirements"]
        assert env.extra["requirements"]["Cython"] == raw["requirements"]["Cython"]
        assert env.extra["requirements"]["numpy"] == "1.8"
