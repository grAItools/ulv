"""Shared test helpers: complete-site builders used across suites.

Plain functions rather than fixtures so tests can parametrize over
them and pass a generator name. Import them with
`from conftest import build_bmf_site` — the tests directory sits on
`sys.path` under pytest's default import mode.
"""

import json
from pathlib import Path

from ulv.cli import main

ASV_FIXTURE = Path(__file__).parent / "fixtures" / "asv_results"


def _generator_flags(generator: str | None) -> list[str]:
    return [] if generator is None else ["--generator", generator]


def build_asv_site(tmp_path: Path, generator: str | None = None) -> Path:
    """Site built from the machine-ful ASV fixture."""
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
                *_generator_flags(generator),
            ]
        )
        == 0
    )
    return out_dir


def _write_bmf_data(tmp_path: Path) -> Path:
    """Materialize the shared BMF data directory (benchmark JSONs +
    manifest) both BMF site builders read from; returns its path."""
    data = tmp_path / "bmf-data"
    data.mkdir(exist_ok=True)
    manifest = {}
    for commit, date, testbed, value in [
        ("c1" * 4, "2026-01-01T00:00:00Z", "linux-x64", 1.0),
        ("c2" * 4, "2026-02-01T00:00:00Z", "linux-x64", 2.0),
        ("c1" * 4, "2026-01-01T00:00:00Z", "macos-arm", 10.0),
        ("c2" * 4, "2026-02-01T00:00:00Z", "macos-arm", 20.0),
    ]:
        name = f"{testbed}-{commit[:2]}.json"
        # a Bencher-style '::' name sanitizes differently on disk, so a
        # frontend fetching raw benchmark names cannot pass by luck
        (data / name).write_text(
            json.dumps({"adapter::json": {"latency": {"value": value}}})
        )
        manifest[name] = {"commit": commit, "date": date, "testbed": testbed}
    (data / "manifest.json").write_text(json.dumps(manifest))
    return data


def build_bmf_site(tmp_path: Path, generator: str | None = None) -> Path:
    """Machine-less BMF site with testbed decomposition."""
    data = _write_bmf_data(tmp_path)
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
                *_generator_flags(generator),
            ]
        )
        == 0
    )
    return out_dir


def build_opaque_bmf_site(tmp_path: Path, generator: str | None = None) -> Path:
    """Same BMF data, no testbed decomposition: single opaque axis."""
    data = _write_bmf_data(tmp_path)
    out_dir = tmp_path / "bmf-opaque-site"
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
                "-o",
                str(out_dir),
                "--project",
                "bmfdemo",
                *_generator_flags(generator),
            ]
        )
        == 0
    )
    return out_dir
