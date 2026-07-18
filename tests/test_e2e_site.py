"""End-to-end crawl of complete sites served from a subdirectory —
the automated stand-in for the manual browser pass (spec: works under a
non-root URL path; no network requests beyond its own static files)."""

import http.server
import json
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
from conftest import build_asv_site, build_bmf_site, build_opaque_bmf_site

_RESOURCE_REF = re.compile(
    r"<(?:script|link|img)\b[^>]*?(?:src|href)\s*=\s*\"([^\"]+)\"", re.IGNORECASE
)

# A script tag carrying type="module" in either attribute order; its
# static imports are followed transitively by _crawl_js_modules.
_MODULE_SCRIPT = re.compile(
    r"<script\b(?=[^>]*type=\"module\")[^>]*src=\"([^\"]+)\"", re.IGNORECASE
)

# `import … from "./x.js"`, bare `import "./x.js"`, and re-exports
# (`export … from "./x.js"`) all bring in a module statically.
_STATIC_IMPORT = re.compile(r"\b(?:import|export)\b[^;]*?[\"'](\.{1,2}/[^\"']+)[\"']")


def _crawl(site: Path) -> None:
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        lambda *args: http.server.SimpleHTTPRequestHandler(
            *args, directory=str(site.parent)
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/{site.name}/"
        html = urllib.request.urlopen(base + "index.html").read().decode()
        targets = ["index.html", "info.json", "index.json"]
        refs = _RESOURCE_REF.findall(html)
        assert refs, "index.html references no assets?"
        for ref in refs:
            assert not re.match(r"^(https?:)?//", ref), ref
        targets += refs
        for target in targets:
            assert urllib.request.urlopen(base + target).status == 200, target
        for css_file in site.rglob("*.css"):
            css_url = base + css_file.relative_to(site).as_posix()
            for ref in re.findall(r"url\(['\"]?([^)'\"]+)", css_file.read_text()):
                if ref.startswith("data:"):
                    continue
                assert not re.match(r"^(https?:)?//", ref), (css_file, ref)
                target = urllib.parse.urljoin(css_url, ref)
                target = target.split("?")[0].split("#")[0]
                assert urllib.request.urlopen(target).status == 200, (css_file, ref)
        # graph data the frontend will fetch lazily
        for graph in site.glob("graphs/**/*.json"):
            rel = urllib.parse.quote(graph.relative_to(site).as_posix())
            assert urllib.request.urlopen(base + rel).status == 200, graph
        crawled = _crawl_js_modules(base, _MODULE_SCRIPT.findall(html))
        # every shipped app module must be reachable from the entry
        # point — an orphaned module is a bug, not just payload
        shipped = {p.relative_to(site).as_posix() for p in site.glob("js/**/*.js")}
        crawled_rel = {urllib.parse.unquote(url[len(base) :]) for url in crawled}
        assert shipped <= crawled_rel, shipped - crawled_rel
        if (site / "index.json").is_file():
            manifest = json.loads((site / "index.json").read_text())["graph_paths"]
            for directory in [*manifest["dirs"], manifest["summary_dir"]]:
                url = base + urllib.parse.quote(directory) + "/"
                assert urllib.request.urlopen(url).status == 200, directory
        if (site / "summarygrid.js").is_file():
            _crawl_grid_summaries(site, base)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _crawl_js_modules(base: str, refs: list[str]) -> set[str]:
    """Fetch every module script and, transitively, every relative
    static-import specifier inside it; returns the crawled URLs so the
    caller can prove the set covers everything shipped."""
    pending = [urllib.parse.urljoin(base, ref) for ref in refs]
    seen: set[str] = set()
    while pending:
        url = pending.pop()
        if url in seen:
            continue
        seen.add(url)
        body = urllib.request.urlopen(url).read().decode()
        for spec in _STATIC_IMPORT.findall(body):
            pending.append(urllib.parse.urljoin(url, spec))
    return seen


# The characters encodeURIComponent leaves unescaped, so the quoted
# path matches what the frontend requests byte-for-byte.
_ENCODE_URI_COMPONENT_SAFE = "!'()*-._~"


def _crawl_grid_summaries(site: Path, base: str) -> None:
    """Fetch each benchmark's grid thumbnail the way the shipped
    summarygrid.js does. The on-disk file lives at the SANITIZED name
    (paths.sanitize_filename), so a frontend fetching the raw name 404s
    for names like 'adapter::json (latency)' — ASV's dotted names only
    passed by coincidence."""
    from ulv.outputs.html.paths import sanitize_filename

    grid_js = (site / "summarygrid.js").read_text()
    patched = "graph_to_path" in grid_js
    if not patched:
        assert "'graphs/summary/' + bm.name" in grid_js, (
            "summarygrid.js fetches summaries some third way; update this mirror"
        )
    index = json.loads((site / "index.json").read_text())
    for name in index["benchmarks"]:
        fetched_name = sanitize_filename(name) if patched else name
        target = (
            base
            + "graphs/summary/"
            + urllib.parse.quote(fetched_name, safe=_ENCODE_URI_COMPONENT_SAFE)
            + ".json"
        )
        assert urllib.request.urlopen(target).status == 200, (name, target)


_MACHINE_GUARD = "index.params.machine !== undefined"


def _frontend_graph_selection(site: Path) -> list:
    """Python mirror of graphdisplay.js's default state setup (:363-379)
    and permutation filter (:768): a graph_param_list candidate is shown
    only when every state key's value list contains the candidate's
    value ($.inArray against undefined always misses). Whether the
    machine key is injected unconditionally mirrors the shipped JS, so
    this fails against an unguarded frontend on machine-less data."""
    index = json.loads((site / "index.json").read_text())
    js = (site / "graphdisplay.js").read_text()
    guarded = _MACHINE_GUARD in js

    state = {}
    if not guarded or "machine" in index["params"]:
        state["machine"] = index["params"].get("machine")
    for param, values in index["params"].items():
        state[param] = values
        if len(values) > 1 and param == "branch":
            state[param] = [values[0]]

    selected = []
    for entry in index["graph_param_list"]:
        if all(
            values is not None and entry.get(key) in values
            for key, values in state.items()
        ):
            selected.append(entry)
    return selected


class TestMachinelessGraphDisplay:
    @pytest.mark.parametrize(
        "builder",
        [build_bmf_site, build_opaque_bmf_site, build_asv_site],
        ids=["bmf-decomposed", "bmf-opaque", "asv"],
    )
    def test_default_state_enumerates_graphs(self, builder, tmp_path):
        site = builder(tmp_path)
        assert _frontend_graph_selection(site), (
            "frontend's default state selects no graphs ('No graphs to load.')"
        )

    def test_machine_guard_shipped_in_frontend(self, tmp_path):
        site = build_bmf_site(tmp_path)
        assert _MACHINE_GUARD in (site / "graphdisplay.js").read_text()
        assert _MACHINE_GUARD in (site / "summarylist.js").read_text()


@pytest.mark.parametrize("generator", [None, "html-uplot"], ids=["html", "html-uplot"])
@pytest.mark.parametrize("builder", [build_asv_site, build_bmf_site])
def test_full_site_crawls_cleanly_from_subdirectory(builder, generator, tmp_path):
    _crawl(builder(tmp_path, generator=generator))


def test_bmf_site_has_decomposed_axes(tmp_path):
    site = build_bmf_site(tmp_path)
    index = json.loads((site / "index.json").read_text())
    assert index["params"]["os"] == ["linux", "macos"]
    assert "testbed" not in index["params"]


def test_bmf_manifest_thumbnails_reachable_on_uplot_site(tmp_path):
    # The grid view derives every thumbnail URL from the manifest
    # (summary_dir + stem); Bencher-style '::' names sanitize
    # differently on disk, so this is the patch-6 bug class of the
    # vendored frontend, now closed by manifest-driven fetching.
    site = build_bmf_site(tmp_path, generator="html-uplot")
    manifest = json.loads((site / "index.json").read_text())["graph_paths"]
    assert any(name != stem for name, stem in manifest["benchmarks"].items())

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        lambda *args: http.server.SimpleHTTPRequestHandler(
            *args, directory=str(site.parent)
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/{site.name}/"
        for stem in manifest["benchmarks"].values():
            path = f"{manifest['summary_dir']}/{stem}.json"
            url = base + "/".join(
                urllib.parse.quote(seg, safe=_ENCODE_URI_COMPONENT_SAFE)
                for seg in path.split("/")
            )
            assert urllib.request.urlopen(url).status == 200, stem
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
