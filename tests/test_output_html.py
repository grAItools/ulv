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


class TestGraphPathsManifest:
    """The additive `graph_paths` key maps every graph data file to an
    explicit on-disk path (dir + "/" + stem + ".json"), so a frontend
    never has to recompute sanitized paths client-side."""

    def test_dirs_parallel_to_graph_param_list(self, index):
        from ulv.outputs.html.paths import graph_path

        manifest = index["graph_paths"]
        assert len(manifest["dirs"]) == len(index["graph_param_list"])
        for entry, directory in zip(index["graph_param_list"], manifest["dirs"]):
            assert directory == graph_path(entry, "x").rsplit("/", 1)[0]

    def test_dirs_exist_on_disk(self, site, index):
        for directory in index["graph_paths"]["dirs"]:
            assert (site / directory).is_dir(), directory

    def test_benchmark_stems_are_sanitized_names(self, index, dataset):
        from ulv.outputs.html.paths import sanitize_filename

        stems = index["graph_paths"]["benchmarks"]
        assert set(stems) == set(dataset.benchmarks)
        for name, stem in stems.items():
            assert stem == sanitize_filename(name)

    def test_summary_dir_has_file_per_stem(self, site, index):
        manifest = index["graph_paths"]
        for stem in manifest["benchmarks"].values():
            assert (site / manifest["summary_dir"] / f"{stem}.json").is_file(), stem

    def test_bmf_graph_files_all_reachable_through_manifest(self, tmp_path):
        # Machine-less BMF site with Bencher-style '::' names: the names
        # sanitize differently on disk, so a frontend fetching raw names
        # cannot pass by luck. Every emitted graph file must be
        # addressable via manifest lookups — dir × benchmark stem, plus
        # each dir's summary-rows file.
        from conftest import build_bmf_site

        site = build_bmf_site(tmp_path)
        index = json.loads((site / "index.json").read_text())
        manifest = index["graph_paths"]
        assert any(name != stem for name, stem in manifest["benchmarks"].items())

        stems = manifest["benchmarks"].values()
        reachable = {
            f"{directory}/{stem}.json"
            for directory in [*manifest["dirs"], manifest["summary_dir"]]
            for stem in stems
        }
        reachable |= {f"{directory}/summary.json" for directory in manifest["dirs"]}
        emitted = {
            path.relative_to(site).as_posix()
            for path in (site / "graphs").rglob("*.json")
        }
        assert emitted
        assert emitted <= reachable


class TestInfoJson:
    def test_info_json_shape(self, site):
        info = json.loads((site / "info.json").read_text())
        assert info["asv-version"].startswith("ulv ")
        assert isinstance(info["timestamp"], int)


class TestServedFromSubdirectory:
    def test_all_referenced_assets_resolve(self, site):
        # The site must work under a non-root URL path (GitHub Pages
        # project page), so serve the site's parent directory and fetch
        # everything relative to the /<site>/ subdirectory.
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


def _raw_results(machine: str, filename: str) -> dict:
    return json.loads((FIXTURE / machine / filename).read_text())


def _env_graph_file(site, benchmark: str, *needles: str) -> Path:
    """The one non-summary graph file for `benchmark` whose directory path
    contains every needle (e.g. 'machine-cheetah', 'numpy-1.8')."""
    matches = [
        path
        for path in (site / "graphs").rglob(f"{benchmark}.json")
        if "summary" not in path.parts
        and all(any(needle in part for part in path.parts) for needle in needles)
    ]
    assert len(matches) == 1, (benchmark, needles, matches)
    return matches[0]


class TestGraphData:
    """Unit tests for the asv/graph.py port (no step detection)."""

    def _graph(self):
        from ulv.outputs.html.graphs import Graph

        return Graph("bench", {"machine": "m"})

    def test_duplicate_revisions_are_arithmetic_averaged(self):
        graph = self._graph()
        graph.add_data_point(5, 1.0)
        graph.add_data_point(5, 3.0)
        assert graph.get_data() == [(5, 2.0, None)]

    def test_na_values_ignored_in_average(self):
        graph = self._graph()
        graph.add_data_point(5, 1.0)
        graph.add_data_point(5, None)
        graph.add_data_point(5, float("nan"))
        assert graph.get_data() == [(5, 1.0, None)]

    def test_leading_and_trailing_all_na_revisions_trimmed(self):
        graph = self._graph()
        graph.add_data_point(1, None)
        graph.add_data_point(2, 1.0)
        graph.add_data_point(3, None)
        graph.add_data_point(4, 2.0)
        graph.add_data_point(5, None)
        data = graph.get_data()
        assert [point[0] for point in data] == [2, 3, 4]
        assert [point[1] for point in data] == [1.0, None, 2.0]

    def test_series_length_mismatch_raises(self):
        graph = self._graph()
        graph.add_data_point(1, [1.0, 2.0])
        with pytest.raises(ValueError, match="[Mm]ismatch"):
            graph.add_data_point(2, [1.0, 2.0, 3.0])

    def test_save_drops_weights_and_never_emits_nan(self, tmp_path):
        graph = self._graph()
        graph.add_data_point(1, 1.0, weight=2.5)
        graph.add_data_point(2, float("nan"))
        graph.add_data_point(3, 3.0)
        graph.save(tmp_path)
        text = (tmp_path / (graph.path + ".json")).read_text()
        assert "NaN" not in text
        assert json.loads(text) == [[1, 1.0], [2, None], [3, 3.0]]


class TestGraphFiles:
    def test_scalar_graph_values_match_fixture(self, site, index):
        graph_file = _env_graph_file(
            site, "time_units.time_unit_parse", "machine-cheetah", "numpy-1.8"
        )
        data = json.loads(graph_file.read_text())
        old = _raw_results("cheetah", "05d4f83d-py2.7-Cython-numpy1.8.json")
        mid = _raw_results("cheetah", "fcf8c079-py2.7-Cython-numpy1.8.json")
        new = _raw_results("cheetah", "05d283b9-py2.7-Cython-numpy1.8.json")
        # The oldest commit's run failed (result null in the raw file), so
        # revision 0 is an all-NA leading edge and gets trimmed.
        assert old["results"]["time_units.time_unit_parse"][0] is None
        expected = [
            [1, mid["results"]["time_units.time_unit_parse"][0][0]],
            [2, new["results"]["time_units.time_unit_parse"][0][0]],
        ]
        assert data == expected
        for revision, commit in [(0, old), (1, mid), (2, new)]:
            assert index["revision_to_hash"][str(revision)] == commit["commit_hash"]

    def test_parameterized_graph_keeps_flat_product_order(self, site):
        graph_file = _env_graph_file(
            site, "params_examples.mem_param", "machine-cheetah", "numpy-1.8"
        )
        data = json.loads(graph_file.read_text())
        mid = _raw_results("cheetah", "fcf8c079-py2.7-Cython-numpy1.8.json")
        new = _raw_results("cheetah", "05d283b9-py2.7-Cython-numpy1.8.json")
        assert data == [
            [1, mid["results"]["params_examples.mem_param"][0]],
            [2, new["results"]["params_examples.mem_param"][0]],
        ]

    def test_trailing_all_failed_revision_trimmed(self, site):
        # track_value's newest commit collapsed to all-null in the fixture,
        # so the series must end at the previous revision.
        graph_file = _env_graph_file(
            site,
            "params_examples.ParamSuite.track_value",
            "machine-cheetah",
            "numpy-1.8",
        )
        data = json.loads(graph_file.read_text())
        assert data == [[0, [1, 2, 3]], [1, [1, 4, None]]]

    def test_each_machine_gets_its_own_graph(self, site):
        _env_graph_file(
            site, "time_units.time_unit_parse", "machine-cheetah", "numpy-1.8"
        )
        _env_graph_file(
            site, "time_units.time_unit_parse", "machine-cheetah", "numpy-1.9"
        )
        _env_graph_file(site, "time_units.time_unit_parse", "machine-leopard")

    def test_graph_param_list_entries_locate_existing_files(self, site, index):
        from ulv.outputs.html.paths import graph_path

        assert index["graph_param_list"]
        for entry in index["graph_param_list"]:
            directory = graph_path(entry, "x").rsplit("/", 1)[0]
            assert (site / directory).is_dir(), entry

    def test_missing_params_filled_with_null_on_axis_and_graphs(self, site, index):
        # Only one environment declares env-ULV_TEST, so the axis gains a
        # null entry and the other environments' graph params carry null.
        assert index["params"]["env-ULV_TEST"] == ["1", None]
        without = [
            entry
            for entry in index["graph_param_list"]
            if entry["env-ULV_TEST"] is None
        ]
        assert len(without) == len(index["graph_param_list"]) - 1

    def test_no_nan_in_any_emitted_graph_json(self, site):
        for path in (site / "graphs").rglob("*.json"):
            assert "NaN" not in path.read_text(), path


class TestSummaryGraphs:
    def test_summary_file_exists_per_benchmark(self, site, dataset):
        for name in dataset.benchmarks:
            assert (site / "graphs" / "summary" / f"{name}.json").is_file(), name

    def test_single_environment_summary_equals_series(self, site):
        # time_ci_small exists in exactly one environment, so the summary
        # geometric mean over one series is the value itself. The newer
        # revision is NaN-skipped; asv's edge trim (graph.py:201-206)
        # keeps one trailing all-NA revision when everything after the
        # first valid point is missing, and the port preserves that.
        data = json.loads(
            (site / "graphs" / "summary" / "time_ci_small.json").read_text()
        )
        assert data == [[1, 3.0], [2, None]]


class TestSummaryList:
    @pytest.fixture(scope="module")
    def cheetah_rows(self, site, index):
        from ulv.outputs.html.paths import graph_path

        (entry,) = [
            e
            for e in index["graph_param_list"]
            if e["machine"] == "cheetah" and e["numpy"] == "1.8"
        ]
        # summarylist.js fetches graph_to_path('summary', state); the file
        # must sit exactly where the frontend recomputes that path.
        path = graph_path(entry, "summary") + ".json"
        return json.loads((site / path).read_text())

    def test_scalar_row_uses_raw_series_tail(self, cheetah_rows):
        (row,) = [r for r in cheetah_rows if r["name"] == "time_units.time_unit_parse"]
        new = _raw_results("cheetah", "05d283b9-py2.7-Cython-numpy1.8.json")
        assert row["idx"] is None
        assert row["last_rev"] == 2
        assert row["last_value"] == new["results"]["time_units.time_unit_parse"][0][0]

    def test_parameterized_rows_have_flat_idx_and_pretty_names(self, cheetah_rows):
        rows = [r for r in cheetah_rows if r["name"] == "params_examples.mem_param"]
        assert [r["idx"] for r in rows] == [0, 1, 2, 3]
        assert rows[0]["pretty_name"] == "params_examples.mem_param(10, 2)"
        assert rows[3]["pretty_name"] == "params_examples.mem_param(20, 3)"
        new = _raw_results("cheetah", "05d283b9-py2.7-Cython-numpy1.8.json")
        assert [r["last_value"] for r in rows] == (
            new["results"]["params_examples.mem_param"][0]
        )

    def test_change_columns_are_null_without_step_detection(self, cheetah_rows):
        for row in cheetah_rows:
            assert row["prev_value"] is None
            assert row["change_rev"] is None

    def test_last_err_is_ci_width_from_tail_weight(self, cheetah_rows):
        # time_ci_small's tail is the mid revision (newest is NaN-trimmed);
        # its stats give ci_99 = [3.1, 3.9], so the error bar is 0.8.
        (row,) = [r for r in cheetah_rows if r["name"] == "time_ci_small"]
        assert row["last_rev"] == 1
        assert row["last_value"] == 3.0
        assert row["last_err"] == pytest.approx(0.8)


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
    site = root / "html"
    HtmlOutputGenerator().generate(dataset, site, {})
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
        # lower/upper cells for throughput are empty, never a zero
        assert throughput_row.count("<td></td>") == 2
        assert ">0<" not in throughput_row

    def test_snapshot_uses_local_bootstrap_only(self, snapshot_site):
        page = (snapshot_site / "snapshot.html").read_text()
        assert "vendor/css/bootstrap.min.css" in page
        for ref in _resource_refs(page):
            assert not re.match(r"^(https?:)?//", ref), ref

    def test_no_graph_data_emitted_for_snapshot(self, snapshot_site):
        assert not (snapshot_site / "index.json").exists()
        assert list((snapshot_site / "graphs").rglob("*.json")) == []


class TestMultiRevisionBmfSite:
    def test_graph_values_follow_metadata_order(self, tmp_path):
        from ulv.inputs.bmf import BmfInputFormat

        root = tmp_path / "bmf"
        root.mkdir()
        files = {
            "x.json": {"bench": {"latency": {"value": 2.0}}},
            "y.json": {"bench": {"latency": {"value": 1.0}}},
        }
        for name, data in files.items():
            (root / name).write_text(json.dumps(data))
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "x.json": {"commit": "x" * 8, "date": "2026-02-01T00:00:00Z"},
                    "y.json": {"commit": "y" * 8, "date": "2026-01-01T00:00:00Z"},
                }
            )
        )
        dataset = BmfInputFormat().load(
            root, {"project": "demo", "manifest": str(root / "manifest.json")}
        )
        site = tmp_path / "site"
        HtmlOutputGenerator().generate(dataset, site, {})
        assert (site / "index.json").is_file()
        assert not (site / "snapshot.html").exists()
        (graph_file,) = [
            p
            for p in (site / "graphs").rglob("bench (latency).json")
            if "summary" not in p.parts
        ]
        # y (older by metadata) is revision 0 despite its later name.
        assert json.loads(graph_file.read_text()) == [[0, 1.0], [1, 2.0]]


class TestPackaging:
    def test_registered_as_builtin_output_generator(self):
        assert isinstance(plugins.output_generators.get("html"), HtmlOutputGenerator)

    def test_static_tree_reachable_via_importlib_resources(self):
        import importlib.resources

        static = importlib.resources.files("ulv.outputs.html") / "static"
        assert (static / "index.html").is_file()
        assert (static / "vendor" / "css" / "bootstrap.min.css").is_file()

    def test_wheel_ships_static_tree_and_licenses(self, tmp_path):
        # An editable install resolves static/ from the source tree;
        # only a real wheel build proves the files ship.
        import shutil
        import subprocess
        import sys
        import zipfile

        uv = shutil.which("uv")
        if uv is None:
            pytest.skip("uv not on PATH")
        project = Path(__file__).parent.parent
        subprocess.run(
            [uv, "build", "--wheel", "-o", str(tmp_path)],
            cwd=project,
            check=True,
            capture_output=True,
        )
        (wheel,) = tmp_path.glob("*.whl")
        names = set(zipfile.ZipFile(wheel).namelist())
        for required in [
            "ulv/outputs/html/static/index.html",
            "ulv/outputs/html/static/vendor/css/bootstrap.min.css",
            "ulv/outputs/html/static/vendor/fonts/glyphicons-halflings-regular.woff",
            "ulv/outputs/html/LICENSES/asv.txt",
            "ulv/outputs/html/VENDORED.md",
            "ulv/outputs/html_uplot/static/index.html",
            "ulv/outputs/html_uplot/static/vendor/uPlot.iife.min.js",
            "ulv/outputs/html_uplot/static/vendor/uPlot.min.css",
            "ulv/outputs/html_uplot/LICENSES/uplot.txt",
            "ulv/outputs/html_uplot/VENDORED.md",
        ]:
            assert required in names, required

        # Build a site from the packaged artifact: a wheel install is an
        # unzip into site-packages, so running from the extracted tree
        # proves the shipped assets are complete and loadable.
        installed = tmp_path / "installed"
        zipfile.ZipFile(wheel).extractall(installed)
        out_dir = tmp_path / "wheel-site"
        code = (
            "from ulv.cli import main\n"
            "raise SystemExit(main(['build', '-i', 'asv', '--input-dir', "
            f"{str(FIXTURE)!r}, '-o', {str(out_dir)!r}, "
            "'--generator', 'html-uplot']))\n"
        )
        subprocess.run(
            [sys.executable, "-c", code],
            env={"PYTHONPATH": str(installed), "PATH": "/usr/bin:/bin"},
            check=True,
            capture_output=True,
        )
        assert (out_dir / "index.html").is_file()
        assert (out_dir / "vendor" / "uPlot.iife.min.js").is_file()
