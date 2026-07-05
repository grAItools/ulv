"""Tests for config loading and precedence (src/ulv/config.py)."""

import json
from pathlib import Path

import pytest

from ulv.cli import main
from ulv.config import Settings, load_settings
from ulv.errors import UlvError

FIXTURE = Path(__file__).parent / "fixtures" / "asv_results"

FILE_VALUES = {
    "input_format": "asv",
    "input_dir": "results",
    "output_dir": "site",
    "project": "fileproj",
    "project_url": "https://example.org/file",
    "show_commit_url": "https://example.org/commit/",
}

FLAG_VALUES = {
    "input_format": "flag-asv",
    "input_dir": "flag-results",
    "output_dir": "flag-site",
    "project": "flagproj",
    "project_url": "https://example.org/flag",
    "show_commit_url": "https://example.org/flag-commit/",
}


def _write_toml(path: Path, values: dict) -> Path:
    lines = [f'{key} = "{value}"' for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n")
    return path


def _write_json(path: Path, values) -> Path:
    path.write_text(json.dumps(values))
    return path


class TestDefaults:
    def test_defaults_without_config_or_flags(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        settings = load_settings(None, {})
        assert settings == Settings()
        assert settings.input_format is None
        assert settings.project == ""
        assert settings.project_url == "#"
        assert settings.show_commit_url == ""

    def test_default_ulv_toml_discovered_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_toml(tmp_path / "ulv.toml", {"project": "from-default-file"})
        assert load_settings(None, {}).project == "from-default-file"


class TestPrecedence:
    def test_toml_file_values_applied(self, tmp_path):
        config = _write_toml(tmp_path / "ulv.toml", FILE_VALUES)
        settings = load_settings(config, {})
        for key, value in FILE_VALUES.items():
            assert getattr(settings, key) == value

    def test_flags_beat_toml_file_for_every_key(self, tmp_path):
        config = _write_toml(tmp_path / "ulv.toml", FILE_VALUES)
        settings = load_settings(config, dict(FLAG_VALUES))
        for key, value in FLAG_VALUES.items():
            assert getattr(settings, key) == value

    def test_flags_beat_json_file_for_every_key(self, tmp_path):
        config = _write_json(tmp_path / "ulv.json", FILE_VALUES)
        settings = load_settings(config, dict(FLAG_VALUES))
        for key, value in FLAG_VALUES.items():
            assert getattr(settings, key) == value

    def test_empty_string_flag_overrides_file_value(self, tmp_path):
        config = _write_toml(tmp_path / "ulv.toml", FILE_VALUES)
        settings = load_settings(config, {"show_commit_url": ""})
        assert settings.show_commit_url == ""

    def test_unset_flags_do_not_mask_file_values(self, tmp_path):
        config = _write_toml(tmp_path / "ulv.toml", FILE_VALUES)
        settings = load_settings(config, {"project": None, "output_dir": None})
        assert settings.project == "fileproj"
        assert settings.output_dir == "site"

    def test_toml_and_json_produce_identical_settings(self, tmp_path):
        toml_settings = load_settings(
            _write_toml(tmp_path / "ulv.toml", FILE_VALUES), {}
        )
        json_settings = load_settings(
            _write_json(tmp_path / "ulv.json", FILE_VALUES), {}
        )
        assert toml_settings == json_settings


class TestMalformedConfig:
    def test_missing_explicit_config_named(self, tmp_path):
        missing = tmp_path / "nope.toml"
        with pytest.raises(UlvError, match="nope.toml"):
            load_settings(missing, {})

    def test_bad_toml_syntax_named(self, tmp_path):
        config = tmp_path / "ulv.toml"
        config.write_text("project = [unclosed")
        with pytest.raises(UlvError, match="ulv.toml"):
            load_settings(config, {})

    def test_bad_json_syntax_named(self, tmp_path):
        config = tmp_path / "ulv.json"
        config.write_text("{not json")
        with pytest.raises(UlvError, match="ulv.json"):
            load_settings(config, {})

    def test_unknown_key_names_key_and_file(self, tmp_path):
        config = _write_toml(tmp_path / "ulv.toml", {"input_fromat": "asv"})
        with pytest.raises(UlvError, match="input_fromat") as excinfo:
            load_settings(config, {})
        assert "ulv.toml" in str(excinfo.value)

    def test_wrong_value_type_names_key(self, tmp_path):
        config = tmp_path / "ulv.toml"
        config.write_text("project = 42\n")
        with pytest.raises(UlvError, match="project"):
            load_settings(config, {})

    def test_non_table_json_named(self, tmp_path):
        config = _write_json(tmp_path / "ulv.json", ["not", "a", "table"])
        with pytest.raises(UlvError, match="ulv.json"):
            load_settings(config, {})


class TestCliIntegration:
    def _config(self, tmp_path, **extra) -> Path:
        values = {
            "input_format": "asv",
            "input_dir": str(FIXTURE),
            "output_dir": str(tmp_path / "site"),
            "project": "cfgproj",
            **extra,
        }
        return _write_toml(tmp_path / "ulv.toml", values)

    def test_build_entirely_from_config_file(self, tmp_path):
        config = self._config(tmp_path)
        rc = main(["build", "--config", str(config)])
        assert rc == 0
        index = json.loads((tmp_path / "site" / "index.json").read_text())
        assert index["project"] == "cfgproj"

    def test_flag_overrides_config_output_dir(self, tmp_path):
        config = self._config(tmp_path)
        rc = main(["build", "--config", str(config), "-o", str(tmp_path / "other")])
        assert rc == 0
        assert (tmp_path / "other" / "index.html").is_file()
        assert not (tmp_path / "site").exists()

    def test_project_urls_reach_index_json(self, tmp_path):
        config = self._config(
            tmp_path,
            project_url="https://example.org/proj",
            show_commit_url="https://example.org/commit/",
        )
        rc = main(["build", "--config", str(config)])
        assert rc == 0
        index = json.loads((tmp_path / "site" / "index.json").read_text())
        assert index["project_url"] == "https://example.org/proj"
        assert index["show_commit_url"] == "https://example.org/commit/"

    def test_malformed_config_exits_nonzero_naming_file(self, tmp_path, capsys):
        config = tmp_path / "ulv.toml"
        config.write_text("input_format = [broken")
        rc = main(["build", "--config", str(config)])
        assert rc == 1
        assert "ulv.toml" in capsys.readouterr().err

    def test_missing_required_setting_exits_nonzero(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        rc = main(["build", "-i", "asv", "--input-dir", str(FIXTURE)])
        assert rc == 1
        assert "output" in capsys.readouterr().err
