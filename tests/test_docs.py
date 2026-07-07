"""Smoke tests for user documentation examples.

These tests verify that the commands documented in docs/user/ work as
described, catching drift between documentation and implementation.
"""

import json
from pathlib import Path

from ulv.cli import main
from ulv.config import load_settings

REPO_ROOT = Path(__file__).parent.parent
ASV_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "asv_results"
BMF_SAMPLES = REPO_ROOT / "docs" / "user" / "samples" / "bmf"


class TestQuickstart:
    """Tests for docs/user/quickstart.md examples."""

    def test_build_asv_fixture(self, tmp_path):
        """The quickstart ulv build command produces a site."""
        out_dir = tmp_path / "site"
        rc = main(
            [
                "build",
                "-i",
                "asv",
                "--input-dir",
                str(ASV_FIXTURE),
                "-o",
                str(out_dir),
            ]
        )
        assert rc == 0
        assert (out_dir / "index.html").is_file()


class TestBmfSamples:
    """Tests for docs/user/bmf.md examples using the sample data."""

    def test_build_bmf_with_manifest(self, tmp_path):
        """The BMF sample builds with its manifest."""
        out_dir = tmp_path / "site"
        rc = main(
            [
                "build",
                "-i",
                "bmf",
                "--input-dir",
                str(BMF_SAMPLES),
                "-o",
                str(out_dir),
                "--manifest",
                str(BMF_SAMPLES / "manifest.json"),
            ]
        )
        assert rc == 0
        assert (out_dir / "index.html").is_file()

    def test_bmf_sample_files_are_valid_json(self):
        """Each BMF sample file is valid JSON."""
        for path in BMF_SAMPLES.glob("*.json"):
            data = json.loads(path.read_text())
            assert isinstance(data, dict)


class TestConfigExamples:
    """Tests for config file parsing in docs/user/config.md."""

    def test_asv_config_parses(self, tmp_path):
        """The ASV example config from docs parses without error."""
        config = tmp_path / "ulv.toml"
        config.write_text(
            """\
input_format = "asv"
input_dir = ".asv/results"
output_dir = "benchmark-site"
project = "My Project"
project_url = "https://github.com/myorg/myproject"
show_commit_url = "https://github.com/myorg/myproject/commit/"
repo = "."
branches = "main,release"
"""
        )
        settings = load_settings(str(config), {})
        assert settings.input_format == "asv"
        assert settings.project == "My Project"
        assert settings.branch_list() == ["main", "release"]

    def test_bencher_config_parses(self, tmp_path):
        """The Bencher API example config from docs parses without error."""
        config = tmp_path / "ulv.toml"
        config.write_text(
            """\
input_format = "bencher-api"
output_dir = "benchmark-site"
bencher_project = "my-project"
project = "My Project"
"""
        )
        settings = load_settings(str(config), {})
        assert settings.input_format == "bencher-api"
        assert settings.bencher_project == "my-project"

    def test_testbeds_config_parses(self, tmp_path):
        """The testbeds example config from docs parses without error."""
        config = tmp_path / "ulv.toml"
        config.write_text(
            """\
input_format = "bmf"
input_dir = "benchmark-results"
output_dir = "site"

[testbeds]
factors = ["os", "arch"]

[testbeds.map.ubuntu-latest-x64]
os = "linux"
arch = "x64"

[testbeds.map.ubuntu-latest-arm64]
os = "linux"
arch = "arm64"

[testbeds.map.macos-14]
os = "macos"
arch = "arm64"

[testbeds.map.windows-latest]
os = "windows"
arch = "x64"
"""
        )
        settings = load_settings(str(config), {})
        assert settings.testbeds is not None
        assert settings.testbeds.factors == ("os", "arch")
        assert settings.testbeds.factor_values("macos-14") == {
            "os": "macos",
            "arch": "arm64",
        }
