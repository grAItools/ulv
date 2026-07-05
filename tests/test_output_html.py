"""Tests for the HTML output generator (src/ulv/outputs/html/generator.py)."""

import http.server
import json
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from ulv import plugins
from ulv.inputs.asv import AsvInputFormat
from ulv.outputs.html.generator import HtmlOutputGenerator

FIXTURE = Path(__file__).parent / "fixtures" / "asv_results"

# File types a static host serves; anything else in the output would
# mean the site is not "only static assets".
STATIC_SUFFIXES = {
    ".html",
    ".js",
    ".css",
    ".json",
    ".png",
    ".ico",
    ".eot",
    ".svg",
    ".ttf",
    ".woff",
}

# Resource-loading references in HTML. Plain <a href> navigation links
# are not fetched while browsing, so they are exempt from the
# no-absolute-URL rule (the vendored navbar keeps its upstream
# attribution link). Vendored JS is not scanned: absolute URLs inside
# comments or string literals are never fetched by the site.
_RESOURCE_REF = re.compile(
    r"<(?:script|link|img)\b[^>]*?(?:src|href)\s*=\s*\"([^\"]+)\"", re.IGNORECASE
)


@pytest.fixture(scope="module")
def dataset():
    return AsvInputFormat().load(FIXTURE, {"project": "demo"})


@pytest.fixture(scope="module")
def site(dataset, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("build") / "html"
    HtmlOutputGenerator().generate(dataset, out_dir, {})
    return out_dir


def _resource_refs(html_text: str) -> list[str]:
    return _RESOURCE_REF.findall(html_text)


class TestSiteSkeleton:
    def test_index_html_and_frontend_assets_present(self, site):
        for name in [
            "index.html",
            "asv.js",
            "asv_ui.js",
            "graphdisplay.js",
            "summarygrid.js",
            "summarylist.js",
            "asv.css",
            "swallow.ico",
            "vendor/jquery-3.3.1.min.js",
            "vendor/css/bootstrap.min.css",
        ]:
            assert (site / name).is_file(), name

    def test_regressions_assets_absent(self, site):
        assert not (site / "regressions.js").exists()
        assert not (site / "regressions.css").exists()
        assert "regressions" not in (site / "index.html").read_text().lower()

    def test_graphs_dir_exists(self, site):
        assert (site / "graphs").is_dir()

    def test_output_contains_only_static_files(self, site):
        for path in site.rglob("*"):
            if path.is_file():
                assert path.suffix in STATIC_SUFFIXES, path

    def test_no_absolute_urls_in_resource_references(self, site):
        for html_file in site.rglob("*.html"):
            for ref in _resource_refs(html_file.read_text()):
                assert not re.match(r"^(https?:)?//", ref), (html_file, ref)
        for css_file in site.rglob("*.css"):
            for url in re.findall(r"url\(['\"]?([^)'\"]+)", css_file.read_text()):
                assert not re.match(r"^(https?:)?//", url), (css_file, url)


@pytest.fixture(scope="module")
def index(site):
    return json.loads((site / "index.json").read_text())


class TestIndexJson:
    def test_has_every_key_the_frontend_reads(self, index):
        assert set(index) >= {
            "project",
            "project_url",
            "show_commit_url",
            "hash_length",
            "revision_to_hash",
            "revision_to_date",
            "params",
            "graph_param_list",
            "benchmarks",
            "machines",
            "tags",
            "pages",
        }

    def test_revisions_enumerated_in_dataset_order(self, index, dataset):
        expected = {
            str(i): revision.commit_hash for i, revision in enumerate(dataset.revisions)
        }
        assert index["revision_to_hash"] == expected

    def test_revision_dates_are_js_milliseconds(self, index, dataset):
        for i, revision in enumerate(dataset.revisions):
            assert index["revision_to_date"][str(i)] == int(
                revision.date.timestamp() * 1000
            )

    def test_params_cover_environment_axes(self, index):
        assert index["params"]["machine"] == ["cheetah", "leopard"]
        assert index["params"]["numpy"] == ["1.8", "1.9"]

    def test_machines_keyed_by_machine_name(self, index):
        assert set(index["machines"]) == {"cheetah", "leopard"}
        assert index["machines"]["cheetah"]["os"] == "Linux (Fedora 20)"

    def test_benchmarks_map_matches_dataset(self, index, dataset):
        assert set(index["benchmarks"]) == set(dataset.benchmarks)
        entry = index["benchmarks"]["params_examples.mem_param"]
        assert entry["param_names"] == ["number", "depth"]
        assert entry["params"] == [["10", "20"], ["2", "3"]]
        assert entry["unit"] == "bytes"

    def test_graph_param_list_has_one_entry_per_environment(self, index, dataset):
        assert len(index["graph_param_list"]) == len(dataset.environments)
        for entry in index["graph_param_list"]:
            assert "machine" in entry

    def test_pages_are_grid_and_list_only(self, index):
        assert index["pages"] == [
            ["", "Grid view", "Display as a agrid"],
            ["summarylist", "List view", "Display as a list"],
        ]

    def test_project_from_dataset(self, index):
        assert index["project"] == "demo"


class TestInfoJson:
    def test_info_json_shape(self, site):
        info = json.loads((site / "info.json").read_text())
        assert info["asv-version"].startswith("ulv ")
        assert isinstance(info["timestamp"], int)


class TestServedFromSubdirectory:
    def test_all_referenced_assets_resolve(self, site):
        # The site must work under a non-root URL path (GitHub Pages
        # project page), so serve the parent of a nested prefix and
        # fetch everything relative to /<prefix>/<site>/.
        serve_root = site.parent
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            lambda *args: http.server.SimpleHTTPRequestHandler(
                *args, directory=str(serve_root)
            ),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}/{site.name}/"
            html = urllib.request.urlopen(base + "index.html").read().decode()
            targets = ["index.html", "info.json", "index.json"]
            targets += _resource_refs(html)
            for target in targets:
                response = urllib.request.urlopen(base + target)
                assert response.status == 200, target
            # url() references inside stylesheets (e.g. bootstrap's
            # ../fonts/… glyphicons) resolve relative to the CSS file.
            for css_file in site.rglob("*.css"):
                css_url = base + css_file.relative_to(site).as_posix()
                for ref in re.findall(r"url\(['\"]?([^)'\"]+)", css_file.read_text()):
                    if ref.startswith("data:"):
                        continue
                    target = urllib.parse.urljoin(css_url, ref)
                    target = target.split("?")[0].split("#")[0]
                    response = urllib.request.urlopen(target)
                    assert response.status == 200, (css_file, ref)
        finally:
            server.shutdown()
            thread.join()


class TestAtomicOutput:
    def test_rebuild_replaces_previous_site(self, dataset, tmp_path):
        out_dir = tmp_path / "html"
        generator = HtmlOutputGenerator()
        generator.generate(dataset, out_dir, {})
        (out_dir / "stale-marker.txt").write_text("old")
        generator.generate(dataset, out_dir, {})
        assert (out_dir / "index.html").is_file()
        assert not (out_dir / "stale-marker.txt").exists()

    def test_failure_leaves_previous_site_intact(self, dataset, tmp_path, monkeypatch):
        out_dir = tmp_path / "html"
        generator = HtmlOutputGenerator()
        generator.generate(dataset, out_dir, {})
        before = sorted(p.name for p in out_dir.iterdir())

        def boom(*args, **kwargs):
            raise RuntimeError("injected build failure")

        monkeypatch.setattr(HtmlOutputGenerator, "_write_site_json", boom)
        with pytest.raises(RuntimeError):
            generator.generate(dataset, out_dir, {})
        assert sorted(p.name for p in out_dir.iterdir()) == before
        assert [p.name for p in tmp_path.iterdir()] == ["html"]

    def test_failure_creates_no_output_dir(self, dataset, tmp_path, monkeypatch):
        out_dir = tmp_path / "html"

        def boom(*args, **kwargs):
            raise RuntimeError("injected build failure")

        monkeypatch.setattr(HtmlOutputGenerator, "_write_site_json", boom)
        with pytest.raises(RuntimeError):
            HtmlOutputGenerator().generate(dataset, out_dir, {})
        assert not out_dir.exists()
        assert list(tmp_path.iterdir()) == []


class TestPackaging:
    def test_registered_as_builtin_output_generator(self):
        assert isinstance(plugins.output_generators.get("html"), HtmlOutputGenerator)

    def test_static_tree_reachable_via_importlib_resources(self):
        import importlib.resources

        static = importlib.resources.files("ulv.outputs.html") / "static"
        assert (static / "index.html").is_file()
        assert (static / "vendor" / "css" / "bootstrap.min.css").is_file()
