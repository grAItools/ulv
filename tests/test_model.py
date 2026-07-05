"""Tests for the core data model (src/ulv/model.py)."""

import datetime as dt

import pytest

from ulv.model import (
    Benchmark,
    Dataset,
    Environment,
    ResultPoint,
    ResultSeries,
    Revision,
)


def _revision(rid: str, **kwargs) -> Revision:
    return Revision(id=rid, **kwargs)


def _dataset(**overrides) -> Dataset:
    """A small consistent dataset: 2 revisions, 2 environments, 1 benchmark."""
    defaults = dict(
        project="demo",
        revisions=(
            _revision("r0", commit_hash="aaa", date=dt.datetime(2026, 1, 1)),
            _revision("r1", commit_hash="bbb", date=dt.datetime(2026, 2, 1)),
        ),
        environments=(
            Environment(
                id="mach1-py311", factors={"machine": "mach1", "python": "3.11"}
            ),
            Environment(
                id="mach2-py312", factors={"machine": "mach2", "python": "3.12"}
            ),
        ),
        benchmarks={"time_sum": Benchmark(name="time_sum", unit="seconds")},
        series=(
            ResultSeries(
                benchmark="time_sum",
                environment="mach1-py311",
                points={"r0": ResultPoint(value=1.0), "r1": ResultPoint(value=2.0)},
            ),
        ),
    )
    defaults.update(overrides)
    return Dataset(**defaults)


class TestRevisionOrdering:
    def test_revisions_keep_construction_order(self):
        ds = _dataset()
        assert [r.id for r in ds.revisions] == ["r0", "r1"]

    def test_duplicate_revision_ids_rejected(self):
        with pytest.raises(ValueError, match="r0"):
            _dataset(revisions=(_revision("r0"), _revision("r0")))

    def test_revision_index_follows_order(self):
        ds = _dataset()
        assert ds.revision_index("r0") == 0
        assert ds.revision_index("r1") == 1


class TestReferentialIntegrity:
    def test_series_with_unknown_benchmark_rejected(self):
        bad = ResultSeries(benchmark="nope", environment="mach1-py311", points={})
        with pytest.raises(ValueError, match="nope"):
            _dataset(series=(bad,))

    def test_series_with_unknown_environment_rejected(self):
        bad = ResultSeries(benchmark="time_sum", environment="nope", points={})
        with pytest.raises(ValueError, match="nope"):
            _dataset(series=(bad,))

    def test_series_with_unknown_revision_rejected(self):
        bad = ResultSeries(
            benchmark="time_sum",
            environment="mach1-py311",
            points={"r99": ResultPoint(value=1.0)},
        )
        with pytest.raises(ValueError, match="r99"):
            _dataset(series=(bad,))

    def test_duplicate_benchmark_environment_series_pair_rejected(self):
        duplicate = ResultSeries(
            benchmark="time_sum",
            environment="mach1-py311",
            points={"r1": ResultPoint(value=9.0)},
        )
        with pytest.raises(ValueError, match="time_sum"):
            _dataset(series=_dataset().series + (duplicate,))

    def test_benchmark_key_must_match_name(self):
        with pytest.raises(ValueError, match="time_sum"):
            _dataset(benchmarks={"wrong_key": Benchmark(name="time_sum")}, series=())

    def test_param_names_and_params_lengths_must_match(self):
        with pytest.raises(ValueError, match="param"):
            Benchmark(name="b", param_names=("n",), params=())


class TestAxisExtraction:
    def test_axes_union_factor_names_with_sorted_values(self):
        ds = _dataset(
            environments=(
                Environment(id="e1", factors={"machine": "mach2", "python": "3.11"}),
                Environment(id="e2", factors={"machine": "mach1", "python": "3.11"}),
                Environment(id="e3", factors={"machine": "mach1", "ram": "8GB"}),
            ),
            series=(),
        )
        assert ds.environment_axes() == {
            "machine": ("mach1", "mach2"),
            "python": ("3.11",),
            "ram": ("8GB",),
        }

    def test_no_environments_no_axes(self):
        ds = _dataset(environments=(), series=())
        assert ds.environment_axes() == {}


class TestSeriesLookup:
    def test_series_for_returns_only_matching_benchmark(self):
        extra = ResultSeries(
            benchmark="time_prod",
            environment="mach2-py312",
            points={"r0": ResultPoint(value=3.0)},
        )
        ds = _dataset(
            benchmarks={
                "time_sum": Benchmark(name="time_sum"),
                "time_prod": Benchmark(name="time_prod"),
            },
            series=_dataset().series + (extra,),
        )
        assert [s.benchmark for s in ds.series_for("time_sum")] == ["time_sum"]
        assert [s.benchmark for s in ds.series_for("time_prod")] == ["time_prod"]

    def test_series_for_unknown_benchmark_is_empty(self):
        assert _dataset().series_for("absent") == ()


class TestHasTimeAxis:
    def test_two_revisions_have_time_axis(self):
        assert _dataset().has_time_axis is True

    def test_single_revision_snapshot_has_no_time_axis(self):
        ds = _dataset(
            revisions=(_revision("r0"),),
            series=(
                ResultSeries(
                    benchmark="time_sum",
                    environment="mach1-py311",
                    points={"r0": ResultPoint(value=1.0)},
                ),
            ),
        )
        assert ds.has_time_axis is False

    def test_empty_dataset_has_no_time_axis(self):
        assert _dataset(revisions=(), series=()).has_time_axis is False


class TestResultPoint:
    def test_bounds_default_to_none_not_zero(self):
        point = ResultPoint(value=1.5)
        assert point.lower is None
        assert point.upper is None

    def test_bounds_preserved(self):
        point = ResultPoint(value=1.5, lower=1.2, upper=1.9)
        assert (point.lower, point.upper) == (1.2, 1.9)


class TestImmutability:
    def test_model_objects_are_frozen(self):
        with pytest.raises(AttributeError):
            _revision("r0").id = "r1"
        with pytest.raises(AttributeError):
            _dataset().project = "other"
