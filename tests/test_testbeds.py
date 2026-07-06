"""Tests for user-supplied testbed decomposition (spec Decisions 8-9).

Covers the four spec criteria: mapped factors become independent axes,
no mapping keeps the opaque testbed axis, an uncovered testbed fails by
default naming every uncovered name with no site emitted, and
--allow-unmapped instead includes them with "unknown" factor values
plus a diagnostic.
"""

import json
from pathlib import Path

import pytest

from ulv.cli import main
from ulv.config import load_settings
from ulv.errors import UlvError

TESTBED_TOML = """\
[testbeds]
factors = ["os", "arch"]

[testbeds.map.linux-x64]
os = "linux"
arch = "x64"

[testbeds.map.macos-arm]
os = "macos"
arch = "arm64"
"""

PARTIAL_TESTBED_TOML = """\
[testbeds]
factors = ["os", "arch"]

[testbeds.map.linux-x64]
os = "linux"
arch = "x64"
"""


def _bmf_data(root: Path) -> Path:
    """Two commits x two testbeds (plus one win-x86 file on the first
    commit) with distinct values per testbed."""
    root.mkdir()
    files = {
        "linux-c1.json": ("c1" * 4, "2026-01-01T00:00:00Z", "linux-x64", 1.0),
        "linux-c2.json": ("c2" * 4, "2026-02-01T00:00:00Z", "linux-x64", 2.0),
        "macos-c1.json": ("c1" * 4, "2026-01-01T00:00:00Z", "macos-arm", 10.0),
        "macos-c2.json": ("c2" * 4, "2026-02-01T00:00:00Z", "macos-arm", 20.0),
        "win-c1.json": ("c1" * 4, "2026-01-01T00:00:00Z", "win-x86", 100.0),
    }
    manifest = {}
    for name, (commit, date, testbed, value) in files.items():
        (root / name).write_text(json.dumps({"bench": {"latency": {"value": value}}}))
        manifest[name] = {"commit": commit, "date": date, "testbed": testbed}
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def _project(tmp_path: Path, testbeds_toml: str, *, with_win: bool = True):
    data = _bmf_data(tmp_path / "data")
    if not with_win:
        (data / "win-c1.json").unlink()
        manifest = json.loads((data / "manifest.json").read_text())
        del manifest["win-c1.json"]
        (data / "manifest.json").write_text(json.dumps(manifest))
    out_dir = tmp_path / "site"
    config = tmp_path / "ulv.toml"
    config.write_text(
        f'input_format = "bmf"\n'
        f'input_dir = "{data}"\n'
        f'output_dir = "{out_dir}"\n'
        f'manifest = "{data / "manifest.json"}"\n'
        f'project = "tb"\n' + testbeds_toml
    )
    return config, out_dir


class TestMappedFactorsBecomeAxes:
    @pytest.fixture
    def site(self, tmp_path):
        config, out_dir = _project(tmp_path, TESTBED_TOML, with_win=False)
        assert main(["build", "--config", str(config)]) == 0
        return out_dir

    def test_declared_factors_are_independent_axes(self, site):
        index = json.loads((site / "index.json").read_text())
        assert index["params"]["os"] == ["linux", "macos"]
        assert index["params"]["arch"] == ["arm64", "x64"]
        assert "testbed" not in index["params"]

    def test_only_real_factor_combinations_have_graphs(self, site):
        index = json.loads((site / "index.json").read_text())
        combos = {(entry["os"], entry["arch"]) for entry in index["graph_param_list"]}
        assert combos == {("linux", "x64"), ("macos", "arm64")}

    def test_selecting_a_factor_value_matches_only_its_testbed(self, site):
        (linux_graph,) = [
            p
            for p in site.glob("graphs/**/os-linux/**/bench (latency).json")
            if "summary" not in p.parts
        ]
        assert json.loads(linux_graph.read_text()) == [[0, 1.0], [1, 2.0]]
        (macos_graph,) = [
            p
            for p in site.glob("graphs/**/os-macos/**/bench (latency).json")
            if "summary" not in p.parts
        ]
        assert json.loads(macos_graph.read_text()) == [[0, 10.0], [1, 20.0]]


class TestNoMappingKeepsOpaqueAxis:
    def test_testbed_stays_single_axis(self, tmp_path):
        config, out_dir = _project(tmp_path, "", with_win=False)
        assert main(["build", "--config", str(config)]) == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert index["params"]["testbed"] == ["linux-x64", "macos-arm"]
        assert "os" not in index["params"]


class TestUncoveredTestbeds:
    def test_default_fails_naming_every_uncovered_testbed(self, tmp_path, capsys):
        config, out_dir = _project(tmp_path, PARTIAL_TESTBED_TOML)
        rc = main(["build", "--config", str(config)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "macos-arm" in err
        assert "win-x86" in err
        assert not out_dir.exists()

    def test_allow_unmapped_builds_with_unknown_values(self, tmp_path, capsys):
        config, out_dir = _project(tmp_path, PARTIAL_TESTBED_TOML)
        rc = main(["build", "--config", str(config), "--allow-unmapped"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "macos-arm" in err
        assert "win-x86" in err
        index = json.loads((out_dir / "index.json").read_text())
        assert index["params"]["os"] == ["linux", "unknown"]
        assert index["params"]["arch"] == ["unknown", "x64"]
        unknown_combos = [
            entry for entry in index["graph_param_list"] if entry["os"] == "unknown"
        ]
        assert unknown_combos
        for entry in unknown_combos:
            assert entry["arch"] == "unknown"

    def test_allow_unmapped_via_config_key(self, tmp_path, capsys):
        config, out_dir = _project(tmp_path, PARTIAL_TESTBED_TOML)
        # top-level key must precede the [testbeds] tables in TOML
        config.write_text("allow_unmapped = true\n" + config.read_text())
        assert main(["build", "--config", str(config)]) == 0
        assert (out_dir / "index.json").is_file()
        assert "win-x86" in capsys.readouterr().err


class TestEnvironmentDetails:
    def test_original_testbed_name_kept_in_extra(self, tmp_path):
        from ulv.inputs.bmf import BmfInputFormat

        data = _bmf_data(tmp_path / "data")
        settings = load_settings(
            _write_config(tmp_path, "allow_unmapped = true\n" + TESTBED_TOML),
            {},
        )
        dataset = BmfInputFormat().load(
            data,
            {
                "manifest": str(data / "manifest.json"),
                "testbeds": settings.testbeds,
                "allow_unmapped": settings.allow_unmapped,
            },
        )
        by_id = {env.id: env for env in dataset.environments}
        assert by_id["linux-x64"].factors == {"os": "linux", "arch": "x64"}
        assert by_id["linux-x64"].extra["testbed"] == "linux-x64"
        assert by_id["win-x86"].factors == {"os": "unknown", "arch": "unknown"}


def _write_config(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "ulv.toml"
    config.write_text(body)
    return config


class TestConfigValidation:
    def test_toml_and_json_testbeds_parity(self, tmp_path):
        toml_settings = load_settings(_write_config(tmp_path, TESTBED_TOML), {})
        json_config = tmp_path / "ulv.json"
        json_config.write_text(
            json.dumps(
                {
                    "testbeds": {
                        "factors": ["os", "arch"],
                        "map": {
                            "linux-x64": {"os": "linux", "arch": "x64"},
                            "macos-arm": {"os": "macos", "arch": "arm64"},
                        },
                    }
                }
            )
        )
        json_settings = load_settings(json_config, {})
        assert toml_settings.testbeds == json_settings.testbeds
        assert toml_settings.testbeds.factors == ("os", "arch")

    def test_entry_missing_declared_factor_named(self, tmp_path):
        config = _write_config(
            tmp_path,
            '[testbeds]\nfactors = ["os", "arch"]\n'
            "[testbeds.map.linux-x64]\nos = 'linux'\n",
        )
        with pytest.raises(UlvError, match="linux-x64") as excinfo:
            load_settings(config, {})
        assert "arch" in str(excinfo.value)

    def test_entry_with_undeclared_factor_named(self, tmp_path):
        config = _write_config(
            tmp_path,
            '[testbeds]\nfactors = ["os"]\n'
            "[testbeds.map.linux-x64]\nos = 'linux'\nram = '16GB'\n",
        )
        with pytest.raises(UlvError, match="ram"):
            load_settings(config, {})

    def test_reserved_factor_name_rejected(self, tmp_path):
        config = _write_config(
            tmp_path, '[testbeds]\nfactors = ["branch"]\n[testbeds.map]\n'
        )
        with pytest.raises(UlvError, match="branch"):
            load_settings(config, {})

    def test_empty_factor_list_rejected(self, tmp_path):
        config = _write_config(tmp_path, "[testbeds]\nfactors = []\n[testbeds.map]\n")
        with pytest.raises(UlvError, match="factors"):
            load_settings(config, {})

    def test_unknown_testbeds_subkey_named(self, tmp_path):
        config = _write_config(tmp_path, '[testbeds]\nfactrs = ["os"]\n')
        with pytest.raises(UlvError, match="factrs"):
            load_settings(config, {})

    def test_empty_factor_name_rejected(self, tmp_path):
        config = _write_config(
            tmp_path, '[testbeds]\nfactors = ["", "os"]\n[testbeds.map]\n'
        )
        with pytest.raises(UlvError, match="factors"):
            load_settings(config, {})

    def test_empty_factor_value_rejected(self, tmp_path):
        config = _write_config(
            tmp_path,
            '[testbeds]\nfactors = ["os"]\n[testbeds.map.linux-x64]\nos = ""\n',
        )
        with pytest.raises(UlvError, match="os"):
            load_settings(config, {})

    def test_allow_unmapped_must_be_boolean(self, tmp_path):
        config = _write_config(tmp_path, 'allow_unmapped = "yes"\n')
        with pytest.raises(UlvError, match="allow_unmapped"):
            load_settings(config, {})

    def test_allow_unmapped_json_boolean(self, tmp_path):
        config = tmp_path / "ulv.json"
        config.write_text(json.dumps({"allow_unmapped": True}))
        assert load_settings(config, {}).allow_unmapped is True

    def test_flag_beats_file_for_allow_unmapped(self, tmp_path):
        config = _write_config(tmp_path, "allow_unmapped = false\n")
        settings = load_settings(config, {"allow_unmapped": True})
        assert settings.allow_unmapped is True


# A standalone testbeds file carries the [testbeds] table body at top
# level: 'factors' and 'map'.
OVERRIDE_TESTBEDS_TOML = """\
factors = ["os", "arch"]

[map.linux-x64]
os = "LNX"
arch = "X64"

[map.macos-arm]
os = "MAC"
arch = "ARM"
"""


class TestTestbedsFileFlag:
    def test_flag_file_wins_over_config_table(self, tmp_path):
        config, out_dir = _project(tmp_path, TESTBED_TOML, with_win=False)
        override = tmp_path / "beds.toml"
        override.write_text(OVERRIDE_TESTBEDS_TOML)
        rc = main(["build", "--config", str(config), "--testbeds-file", str(override)])
        assert rc == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert index["params"]["os"] == ["LNX", "MAC"]
        assert index["params"]["arch"] == ["ARM", "X64"]

    def test_json_testbeds_file(self, tmp_path):
        config, out_dir = _project(tmp_path, "", with_win=False)
        override = tmp_path / "beds.json"
        override.write_text(
            json.dumps(
                {
                    "factors": ["os", "arch"],
                    "map": {
                        "linux-x64": {"os": "LNX", "arch": "X64"},
                        "macos-arm": {"os": "MAC", "arch": "ARM"},
                    },
                }
            )
        )
        rc = main(["build", "--config", str(config), "--testbeds-file", str(override)])
        assert rc == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert index["params"]["os"] == ["LNX", "MAC"]

    def test_missing_testbeds_file_named(self, tmp_path, capsys):
        config, _ = _project(tmp_path, "", with_win=False)
        rc = main(
            [
                "build",
                "--config",
                str(config),
                "--testbeds-file",
                str(tmp_path / "nope.toml"),
            ]
        )
        assert rc == 1
        assert "nope.toml" in capsys.readouterr().err

    def test_malformed_testbeds_file_named(self, tmp_path, capsys):
        config, _ = _project(tmp_path, "", with_win=False)
        override = tmp_path / "beds.toml"
        override.write_text("factors = [broken")
        rc = main(["build", "--config", str(config), "--testbeds-file", str(override)])
        assert rc == 1
        assert "beds.toml" in capsys.readouterr().err
