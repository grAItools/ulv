"""Tests for the uPlot output generator (src/ulv/outputs/html_uplot/).

The frontend here is self-authored end to end, so the guard rails are
stricter than the vendored suite's: the payload budget is enforced in
bytes, the vendored chart library is hash-pinned, and the absolute-URL
scan covers JS too.
"""

import hashlib
import importlib.resources
import json
import re
from pathlib import Path

import pytest
from conftest import ASV_FIXTURE, build_asv_site

from ulv import plugins
from ulv.cli import main
from ulv.inputs.asv import AsvInputFormat
from ulv.outputs.html_uplot.generator import HtmlUplotOutputGenerator

# Decimal reading of the spec's "<100 KB" budget (plan: Architecture
# decisions), covering everything shipped besides data files.
PAYLOAD_BUDGET_BYTES = 100_000

# Pinned sha256 of the vendored uPlot 1.6.32 files; the same digests
# were verified against both the npm registry tarball and jsDelivr at
# vendoring time (see html_uplot/VENDORED.md).
UPLOT_SHA256 = {
    "uPlot.iife.min.js": (
        "19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f"
    ),
    "uPlot.min.css": (
        "df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04"
    ),
}

STATIC_SUFFIXES = {".html", ".js", ".css", ".json", ".png", ".ico", ".svg"}

_RESOURCE_REF = re.compile(
    r"<(?:script|link|img)\b[^>]*?(?:src|href)\s*=\s*\"([^\"]+)\"", re.IGNORECASE
)

# License banners (/*! ... */) may cite the upstream repository URL;
# nothing in a comment is ever fetched, and the vendored files are
# hash-pinned so the banner cannot be stripped without failing the pin.
_LICENSE_BANNER = re.compile(r"/\*!.*?\*/", re.DOTALL)


def _package_root() -> Path:
    root = importlib.resources.files("ulv.outputs.html_uplot")
    return Path(str(root))


def _static_root() -> Path:
    return _package_root() / "static"


def _resource_refs(html_text: str) -> list[str]:
    return _RESOURCE_REF.findall(html_text)


@pytest.fixture(scope="module")
def dataset():
    return AsvInputFormat().load(ASV_FIXTURE, {"project": "demo"})


@pytest.fixture(scope="module")
def site(dataset, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("build") / "html-uplot"
    HtmlUplotOutputGenerator().generate(dataset, out_dir, {})
    return out_dir


class TestPayloadBudget:
    def test_total_static_payload_under_budget(self):
        total = sum(
            path.stat().st_size for path in _static_root().rglob("*") if path.is_file()
        )
        assert 0 < total < PAYLOAD_BUDGET_BYTES, total


class TestVendoredUplot:
    def test_vendored_files_match_pinned_hashes(self):
        vendor = _static_root() / "vendor"
        for name, expected in UPLOT_SHA256.items():
            digest = hashlib.sha256((vendor / name).read_bytes()).hexdigest()
            assert digest == expected, name

    def test_vendoring_record_carries_hashes_and_sources(self):
        record = (_package_root() / "VENDORED.md").read_text()
        for name, expected in UPLOT_SHA256.items():
            assert name in record
            assert expected in record
        # both independent provenance sources are recorded
        assert "registry.npmjs.org" in record
        assert "cdn.jsdelivr.net" in record

    def test_uplot_license_attributed(self):
        text = (_package_root() / "LICENSES" / "uplot.txt").read_text()
        assert "MIT License" in text
        assert "Leon Sorokin" in text


class TestStaticTree:
    def test_no_absolute_urls_anywhere(self):
        # Stricter than the vendored suite: this frontend is ours end to
        # end, so JS is scanned too, not just HTML/CSS references. Only
        # hash-pinned files under vendor/ get the license-banner
        # carve-out; the self-authored tree is scanned raw.
        for path in _static_root().rglob("*"):
            if not path.is_file() or path.suffix not in {".html", ".css", ".js"}:
                continue
            text = path.read_text()
            if path.is_relative_to(_static_root() / "vendor"):
                text = _LICENSE_BANNER.sub("", text)
            assert not re.search(r"https?://", text), path
            for ref in _resource_refs(text):
                assert not ref.startswith("//"), (path, ref)
            for url in re.findall(r"url\(['\"]?([^)'\"]+)", text):
                assert not url.startswith("//"), (path, url)

    def test_app_shell_js_never_mentions_machine(self):
        # Spec Decision 4: machine is an ordinary parameter axis, so
        # machine-less datasets work because axes are generic — the app
        # shell must not special-case (or even mention) the word.
        for path in (_static_root() / "js").rglob("*.js"):
            assert "machine" not in path.read_text().lower(), path

    def test_app_shell_js_builds_no_graph_paths_by_hand(self):
        # Every graph URL comes from the graph_paths manifest; no module
        # may assemble a "graphs/..." path from raw benchmark names (the
        # sanitized-path bug class the manifest exists to kill).
        for path in (_static_root() / "js").rglob("*.js"):
            text = path.read_text()
            assert '"graphs/' not in text, path
            assert "'graphs/" not in text, path
            assert "`graphs/" not in text, path
        assert "graph_paths" in (_static_root() / "js" / "data.js").read_text()

    def test_graph_view_wires_overview_and_touch(self):
        # The ranger and the touch plugin only work if the graph view
        # actually mounts them; reachability via the module crawl alone
        # would also pass for dead imports elsewhere.
        text = (_static_root() / "js" / "views" / "graph.js").read_text()
        assert "./overview.js" in text
        assert "../touch.js" in text

    def test_main_wires_grid_and_list_views(self):
        text = (_static_root() / "js" / "main.js").read_text()
        assert "./views/grid.js" in text
        assert "./views/list.js" in text

    def test_dead_columns_absent_from_shipped_app_code(self):
        # Spec Decision 5: ulv always emits null for the step-detection
        # columns, so the list view drops them instead of shipping dead
        # UI — the strings must not appear anywhere we author.
        for path in _static_root().rglob("*"):
            if not path.is_file() or path.suffix not in {".html", ".css", ".js"}:
                continue
            if path.is_relative_to(_static_root() / "vendor"):
                continue
            text = path.read_text()
            assert "Recent change" not in text, path
            assert "Changed at" not in text, path

    def test_index_html_is_mobile_ready_app_shell(self):
        page = (_static_root() / "index.html").read_text()
        assert re.search(r"<meta\s+name=\"viewport\"", page)
        refs = _resource_refs(page)
        assert "vendor/uPlot.iife.min.js" in refs
        assert "vendor/uPlot.min.css" in refs
        assert "app.css" in refs
        assert 'type="module"' in page
        assert "js/main.js" in refs


class TestSite:
    def test_output_contains_only_static_files(self, site):
        for path in site.rglob("*"):
            if path.is_file():
                assert path.suffix in STATIC_SUFFIXES, path

    def test_emits_same_data_contract_as_vendored_generator(self, site):
        index = json.loads((site / "index.json").read_text())
        assert "graph_paths" in index
        assert (site / "info.json").is_file()
        assert list((site / "graphs").rglob("*.json"))

    def test_vendored_asv_frontend_not_shipped(self, site):
        assert not (site / "asv.js").exists()
        assert not (site / "vendor" / "jquery-3.3.1.min.js").exists()


class TestGeneratorSelection:
    def test_registered_as_builtin_output_generator(self):
        generator = plugins.output_generators.get("html-uplot")
        assert isinstance(generator, HtmlUplotOutputGenerator)

    def test_cli_generator_flag_selects_uplot_frontend(self, tmp_path):
        site = build_asv_site(tmp_path, generator="html-uplot")
        assert (site / "vendor" / "uPlot.iife.min.js").is_file()
        assert not (site / "asv.js").exists()

    def test_default_build_still_uses_vendored_frontend(self, tmp_path):
        site = build_asv_site(tmp_path)
        assert (site / "asv.js").is_file()
        assert not (site / "vendor" / "uPlot.iife.min.js").exists()

    def test_unknown_generator_lists_available_names(self, tmp_path, capsys):
        rc = main(
            [
                "build",
                "-i",
                "asv",
                "--input-dir",
                str(ASV_FIXTURE),
                "-o",
                str(tmp_path / "site"),
                "--generator",
                "nope",
            ]
        )
        assert rc == 1
        err = capsys.readouterr().err
        assert "nope" in err
        assert "html-uplot" in err


BMF_SNAPSHOT = {
    "adapter::json": {
        "latency": {"value": 3.5, "lower_value": 3.1, "upper_value": 4.0},
        "throughput": {"value": 100.0},
    },
}


@pytest.fixture(scope="module")
def snapshot_site(tmp_path_factory):
    from ulv.inputs.bmf import BmfInputFormat

    root = tmp_path_factory.mktemp("bmf")
    source = root / "snap.json"
    source.write_text(json.dumps(BMF_SNAPSHOT))
    dataset = BmfInputFormat().load(source, {"project": "snapdemo"})
    site = root / "html-uplot"
    HtmlUplotOutputGenerator().generate(dataset, site, {})
    return site


class TestSnapshotPage:
    def test_snapshot_html_is_the_entry_point(self, snapshot_site):
        assert (snapshot_site / "snapshot.html").is_file()
        index = (snapshot_site / "index.html").read_text()
        assert "snapshot.html" in index
        assert 'http-equiv="refresh"' in index

    def test_rows_show_values_and_bounds(self, snapshot_site):
        page = (snapshot_site / "snapshot.html").read_text()
        assert "adapter::json" in page
        assert "latency" in page
        assert "3.5" in page
        assert "3.1" in page
        assert "4.0" in page

    def test_absent_bounds_render_empty_not_zero(self, snapshot_site):
        page = (snapshot_site / "snapshot.html").read_text()
        throughput_row = next(
            line for line in page.splitlines() if "throughput" in line
        )
        assert "100.0" in throughput_row
        assert throughput_row.count("<td></td>") == 2
        assert ">0<" not in throughput_row

    def test_snapshot_uses_own_local_css_and_no_js(self, snapshot_site):
        page = (snapshot_site / "snapshot.html").read_text()
        assert "app.css" in page
        assert "<script" not in page
        for ref in _resource_refs(page):
            assert not re.match(r"^(https?:)?//", ref), ref

    def test_no_graph_data_emitted_for_snapshot(self, snapshot_site):
        assert not (snapshot_site / "index.json").exists()
        assert list((snapshot_site / "graphs").rglob("*.json")) == []


class TestAtomicOutput:
    def test_rebuild_replaces_previous_site(self, dataset, tmp_path):
        out_dir = tmp_path / "html-uplot"
        generator = HtmlUplotOutputGenerator()
        generator.generate(dataset, out_dir, {})
        (out_dir / "stale-marker.txt").write_text("old")
        generator.generate(dataset, out_dir, {})
        assert (out_dir / "index.html").is_file()
        assert not (out_dir / "stale-marker.txt").exists()

    def test_failure_leaves_previous_site_intact(self, dataset, tmp_path, monkeypatch):
        out_dir = tmp_path / "html-uplot"
        generator = HtmlUplotOutputGenerator()
        generator.generate(dataset, out_dir, {})
        before = sorted(p.name for p in out_dir.iterdir())

        def boom(*args, **kwargs):
            raise RuntimeError("injected build failure")

        monkeypatch.setattr(HtmlUplotOutputGenerator, "_write_site_json", boom)
        with pytest.raises(RuntimeError):
            generator.generate(dataset, out_dir, {})
        assert sorted(p.name for p in out_dir.iterdir()) == before
        assert [p.name for p in tmp_path.iterdir()] == ["html-uplot"]

    def test_failure_creates_no_output_dir(self, dataset, tmp_path, monkeypatch):
        out_dir = tmp_path / "html-uplot"

        def boom(*args, **kwargs):
            raise RuntimeError("injected build failure")

        monkeypatch.setattr(HtmlUplotOutputGenerator, "_write_site_json", boom)
        with pytest.raises(RuntimeError):
            HtmlUplotOutputGenerator().generate(dataset, out_dir, {})
        assert not out_dir.exists()
        assert list(tmp_path.iterdir()) == []
