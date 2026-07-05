"""Tests for the plugin protocols and registry (src/ulv/plugins.py)."""

import json

import pytest

from ulv import plugins
from ulv.errors import UlvError
from ulv.model import (
    Benchmark,
    Dataset,
    Environment,
    ResultPoint,
    ResultSeries,
    Revision,
)
from ulv.plugins import InputFormat, OutputGenerator, Registry

CANNED_DATASET = Dataset(
    project="canned",
    revisions=(Revision(id="r0"), Revision(id="r1")),
    environments=(Environment(id="env1", factors={"machine": "m1"}),),
    benchmarks={"time_it": Benchmark(name="time_it", unit="seconds")},
    series=(
        ResultSeries(
            benchmark="time_it",
            environment="env1",
            points={"r0": ResultPoint(value=1.0), "r1": ResultPoint(value=2.0)},
        ),
    ),
)


class DummyInput:
    name = "dummy-in"

    def load(self, source, options):
        return CANNED_DATASET


class DummyOutput:
    name = "dummy-out"

    def generate(self, dataset, out_dir, options):
        dump = {
            "project": dataset.project,
            "revisions": [r.id for r in dataset.revisions],
            "values": {
                s.benchmark: {rid: p.value for rid, p in s.points.items()}
                for s in dataset.series
            },
        }
        (out_dir / "dump.json").write_text(json.dumps(dump))


class TestProtocols:
    def test_dummy_input_satisfies_protocol(self):
        assert isinstance(DummyInput(), InputFormat)

    def test_dummy_output_satisfies_protocol(self):
        assert isinstance(DummyOutput(), OutputGenerator)

    def test_object_without_load_is_not_an_input_format(self):
        assert not isinstance(DummyOutput(), InputFormat)


class TestRegistry:
    def test_register_get_names_round_trip(self):
        reg = Registry(plugins.INPUT_GROUP)
        plugin = DummyInput()
        reg.register(plugin)
        assert reg.get("dummy-in") is plugin
        assert reg.names() == ["dummy-in"]

    def test_duplicate_name_rejected(self):
        reg = Registry(plugins.INPUT_GROUP)
        reg.register(DummyInput())
        with pytest.raises(ValueError, match="dummy-in"):
            reg.register(DummyInput())

    def test_get_unknown_name_is_ulv_error_naming_it(self):
        reg = Registry(plugins.INPUT_GROUP)
        with pytest.raises(UlvError, match="no-such-format"):
            reg.get("no-such-format")

    def test_registering_elsewhere_leaves_builtin_registries_untouched(self):
        before_inputs = plugins.input_formats.names()
        before_outputs = plugins.output_generators.names()
        reg = Registry(plugins.INPUT_GROUP)
        reg.register(DummyInput())
        assert plugins.input_formats.names() == before_inputs
        assert plugins.output_generators.names() == before_outputs


class TestEndToEnd:
    def test_dummy_input_to_dummy_output_via_registries(self, tmp_path):
        inputs = Registry(plugins.INPUT_GROUP)
        outputs = Registry(plugins.OUTPUT_GROUP)
        inputs.register(DummyInput())
        outputs.register(DummyOutput())

        dataset = inputs.get("dummy-in").load(source=None, options={})
        outputs.get("dummy-out").generate(dataset, tmp_path, options={})

        dump = json.loads((tmp_path / "dump.json").read_text())
        assert dump["project"] == "canned"
        assert dump["revisions"] == ["r0", "r1"]
        assert dump["values"] == {"time_it": {"r0": 1.0, "r1": 2.0}}


class FakeEntryPoint:
    def __init__(self, name, obj):
        self.name = name
        self._obj = obj

    def load(self):
        return self._obj


class TestEntryPointDiscovery:
    @pytest.fixture
    def fake_entry_points(self, monkeypatch):
        def entry_points(*, group):
            if group == plugins.INPUT_GROUP:
                return [FakeEntryPoint("ep-in", DummyInput)]
            if group == plugins.OUTPUT_GROUP:
                return [FakeEntryPoint("ep-out", DummyOutput())]
            return []

        monkeypatch.setattr(plugins, "entry_points", entry_points)

    def test_discovers_input_entry_points(self, fake_entry_points):
        reg = Registry(plugins.INPUT_GROUP)
        assert "ep-in" in reg.names()
        assert isinstance(reg.get("ep-in"), DummyInput)

    def test_discovers_output_entry_points(self, fake_entry_points):
        reg = Registry(plugins.OUTPUT_GROUP)
        assert "ep-out" in reg.names()
        assert isinstance(reg.get("ep-out"), DummyOutput)

    def test_explicit_registration_wins_over_entry_point(self, fake_entry_points):
        reg = Registry(plugins.INPUT_GROUP)
        mine = DummyInput()
        mine.name = "ep-in"
        reg.register(mine)
        assert reg.get("ep-in") is mine
