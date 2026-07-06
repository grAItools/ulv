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

from ulv.cli import main

ASV_FIXTURE = Path(__file__).parent / "fixtures" / "asv_results"

_RESOURCE_REF = re.compile(
    r"<(?:script|link|img)\b[^>]*?(?:src|href)\s*=\s*\"([^\"]+)\"", re.IGNORECASE
)


def _build_asv_site(tmp_path: Path) -> Path:
    out_dir = tmp_path / "asv-site"
    assert (
        main(
            [
                "build",
                "-i",
                "asv",
                "--input-dir",
                str(ASV_FIXTURE),
                "-o",
                str(out_dir),
                "--project",
                "demo",
            ]
        )
        == 0
    )
    return out_dir


def _build_bmf_site(tmp_path: Path) -> Path:
    data = tmp_path / "bmf-data"
    data.mkdir()
    manifest = {}
    for commit, date, testbed, value in [
        ("c1" * 4, "2026-01-01T00:00:00Z", "linux-x64", 1.0),
        ("c2" * 4, "2026-02-01T00:00:00Z", "linux-x64", 2.0),
        ("c1" * 4, "2026-01-01T00:00:00Z", "macos-arm", 10.0),
        ("c2" * 4, "2026-02-01T00:00:00Z", "macos-arm", 20.0),
    ]:
        name = f"{testbed}-{commit[:2]}.json"
        (data / name).write_text(json.dumps({"bench": {"latency": {"value": value}}}))
        manifest[name] = {"commit": commit, "date": date, "testbed": testbed}
    (data / "manifest.json").write_text(json.dumps(manifest))
    beds = tmp_path / "beds.toml"
    beds.write_text(
        'factors = ["os", "arch"]\n'
        '[map.linux-x64]\nos = "linux"\narch = "x64"\n'
        '[map.macos-arm]\nos = "macos"\narch = "arm64"\n'
    )
    out_dir = tmp_path / "bmf-site"
    assert (
        main(
            [
                "build",
                "-i",
                "bmf",
                "--input-dir",
                str(data),
                "--manifest",
                str(data / "manifest.json"),
                "--testbeds-file",
                str(beds),
                "-o",
                str(out_dir),
                "--project",
                "bmfdemo",
            ]
        )
        == 0
    )
    return out_dir


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
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.mark.parametrize("builder", [_build_asv_site, _build_bmf_site])
def test_full_site_crawls_cleanly_from_subdirectory(builder, tmp_path):
    _crawl(builder(tmp_path))


def test_bmf_site_has_decomposed_axes(tmp_path):
    site = _build_bmf_site(tmp_path)
    index = json.loads((site / "index.json").read_text())
    assert index["params"]["os"] == ["linux", "macos"]
    assert "testbed" not in index["params"]
