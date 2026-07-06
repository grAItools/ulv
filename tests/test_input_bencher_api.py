"""Tests for the Bencher REST API input (src/ulv/inputs/bencher_api.py).

No live network anywhere: unit tests inject a fake transport returning
the recorded fixtures, and the one integration test runs the real
urllib transport against a local http.server stub.
"""

import datetime as dt
import http.server
import json
import threading
import urllib.parse
from pathlib import Path

import pytest

from ulv import plugins
from ulv.cli import main
from ulv.errors import UlvError
from ulv.inputs import bencher_api
from ulv.inputs.bencher_api import BencherApiInputFormat
from ulv.inputs.bmf import BmfInputFormat
from ulv.outputs.html.generator import HtmlOutputGenerator
from ulv.testbeds import parse_testbeds

FIXTURE = Path(__file__).parent / "fixtures" / "bencher_api"
REPORTS = json.loads((FIXTURE / "reports.json").read_text())

C1, C2 = "a" * 40, "b" * 40
SECRET = "SECRET-TOKEN-VALUE"


class FakeTransport:
    """Slices the fixture report list according to page/per_page, like
    the real endpoint; can be forced into error modes."""

    def __init__(self, reports=REPORTS, status=200, body=None):
        self.reports = reports
        self.status = status
        self.body = body
        self.requests: list[tuple[str, dict]] = []

    def get(self, url, headers):
        self.requests.append((url, dict(headers)))
        if self.body is not None or self.status != 200:
            return self.status, self.body if self.body is not None else b"[]"
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        page = int(query["page"][0])
        per_page = int(query["per_page"][0])
        start = (page - 1) * per_page
        chunk = self.reports[start : start + per_page]
        return 200, json.dumps(chunk).encode()


def _load(transport=None, **options):
    transport = transport or FakeTransport()
    return BencherApiInputFormat().load(
        None,
        {
            "project": "demo",
            "bencher_project": "demo",
            "transport": transport,
            **options,
        },
    )


class TestFetchedDataset:
    def test_revisions_ordered_by_report_dates(self):
        dataset = _load()
        assert [r.id for r in dataset.revisions] == [C1, C2]
        assert dataset.revisions[0].date == dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        assert dataset.revisions[0].branch == "main"

    def test_values_and_bounds_match_fixture(self):
        dataset = _load()
        (series,) = [
            s
            for s in dataset.series_for("adapter::json (latency)")
            if s.environment == "linux-x64"
        ]
        point = series.points[C1]
        assert (point.value, point.lower, point.upper) == (3.5, 3.1, 4.0)

    def test_absent_bounds_stay_none(self):
        dataset = _load()
        (series,) = [
            s
            for s in dataset.series_for("adapter::json (throughput)")
            if s.environment == "macos-arm"
        ]
        assert series.points[C2].lower is None
        assert series.points[C2].upper is None

    def test_testbeds_become_opaque_environments(self):
        dataset = _load()
        assert sorted(e.id for e in dataset.environments) == [
            "linux-x64",
            "macos-arm",
        ]
        assert dataset.environment_axes()["testbed"] == ("linux-x64", "macos-arm")

    def test_testbed_decomposition_applies(self):
        config = parse_testbeds(
            {
                "factors": ["os", "arch"],
                "map": {
                    "linux-x64": {"os": "linux", "arch": "x64"},
                    "macos-arm": {"os": "macos", "arch": "arm64"},
                },
            },
            "inline",
        )
        dataset = _load(testbeds=config)
        by_id = {env.id: env for env in dataset.environments}
        assert by_id["linux-x64"].factors == {"os": "linux", "arch": "x64"}
        assert by_id["linux-x64"].extra["testbed"] == "linux-x64"

    def test_registered_as_builtin(self):
        assert isinstance(
            plugins.input_formats.get("bencher-api"), BencherApiInputFormat
        )


class TestSiteEquivalence:
    def _bmf_site(self, root):
        """Local BMF files equivalent to the recorded API reports."""
        data = root / "bmf"
        data.mkdir()
        files = {
            "r1.json": (
                C1,
                "2026-01-01T00:00:00Z",
                "linux-x64",
                {
                    "adapter::json": {
                        "latency": {
                            "value": 3.5,
                            "lower_value": 3.1,
                            "upper_value": 4.0,
                        },
                        "throughput": {"value": 100.0},
                    },
                    "parser": {"latency": {"value": 7.0}},
                },
            ),
            "r2.json": (
                C1,
                "2026-01-01T00:00:00Z",
                "macos-arm",
                {
                    "adapter::json": {
                        "latency": {
                            "value": 9.5,
                            "lower_value": 9.0,
                            "upper_value": 10.0,
                        },
                        "throughput": {"value": 50.0},
                    }
                },
            ),
            "r3.json": (
                C2,
                "2026-02-01T00:00:00Z",
                "linux-x64",
                {
                    "adapter::json": {
                        "latency": {
                            "value": 3.0,
                            "lower_value": 2.9,
                            "upper_value": 3.2,
                        },
                        "throughput": {"value": 110.0},
                    },
                    "parser": {"latency": {"value": 6.5}},
                },
            ),
            "r4.json": (
                C2,
                "2026-02-01T00:00:00Z",
                "macos-arm",
                {
                    "adapter::json": {
                        "latency": {
                            "value": 9.0,
                            "lower_value": 8.8,
                            "upper_value": 9.4,
                        },
                        "throughput": {"value": 55.0},
                    }
                },
            ),
        }
        manifest = {}
        for name, (commit, date, testbed, content) in files.items():
            (data / name).write_text(json.dumps(content))
            manifest[name] = {
                "commit": commit,
                "date": date,
                "branch": "main",
                "testbed": testbed,
            }
        (data / "manifest.json").write_text(json.dumps(manifest))
        dataset = BmfInputFormat().load(
            data, {"project": "demo", "manifest": str(data / "manifest.json")}
        )
        site = root / "bmf-site"
        HtmlOutputGenerator().generate(dataset, site, {})
        return site

    def test_fetched_site_identical_to_local_bmf_site(self, tmp_path):
        api_site = tmp_path / "api-site"
        HtmlOutputGenerator().generate(_load(), api_site, {})
        bmf_site = self._bmf_site(tmp_path)

        api_index = json.loads((api_site / "index.json").read_text())
        bmf_index = json.loads((bmf_site / "index.json").read_text())
        assert api_index == bmf_index

        api_graphs = {
            p.relative_to(api_site).as_posix(): p.read_text()
            for p in (api_site / "graphs").rglob("*.json")
        }
        bmf_graphs = {
            p.relative_to(bmf_site).as_posix(): p.read_text()
            for p in (bmf_site / "graphs").rglob("*.json")
        }
        assert api_graphs == bmf_graphs


class TestPagination:
    def test_short_page_terminates_iteration(self, monkeypatch):
        monkeypatch.setattr(bencher_api, "PER_PAGE", 2)
        transport = FakeTransport()
        dataset = _load(transport=transport)
        pages = [
            urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["page"][0]
            for url, _ in transport.requests
        ]
        # 4 reports at 2 per page: two full pages, then the empty one.
        assert pages == ["1", "2", "3"]
        assert [r.id for r in dataset.revisions] == [C1, C2]


class TestErrors:
    def test_401_is_a_clear_auth_error_without_token(self):
        transport = FakeTransport(status=401, body=b'{"error": "unauthorized"}')
        with pytest.raises(UlvError) as excinfo:
            _load(transport=transport, bencher_token=SECRET)
        message = str(excinfo.value)
        assert "401" in message
        assert "token" in message.lower()
        assert SECRET not in message

    @pytest.mark.parametrize(
        ("status", "body"),
        [
            (500, b"boom"),
            (200, b"{not json"),
            (200, b'{"unexpected": "object"}'),
            (200, b'[{"broken": true}]'),
        ],
    )
    def test_token_never_appears_in_any_error(self, status, body):
        transport = FakeTransport(status=status, body=body)
        with pytest.raises(UlvError) as excinfo:
            _load(transport=transport, bencher_token=SECRET)
        assert SECRET not in str(excinfo.value)
        assert SECRET not in repr(excinfo.value.offending_input)

    def test_malformed_payload_names_endpoint(self):
        transport = FakeTransport(status=200, body=b"{not json")
        with pytest.raises(UlvError, match="/v0/projects/demo/reports"):
            _load(transport=transport)

    def test_missing_project_setting(self):
        with pytest.raises(UlvError, match="bencher_project"):
            BencherApiInputFormat().load(None, {"transport": FakeTransport()})


class TestToken:
    def test_token_from_env_var_sent_as_bearer(self, monkeypatch):
        monkeypatch.setenv("BENCHER_API_TOKEN", "env-token")
        transport = FakeTransport()
        _load(transport=transport)
        _, headers = transport.requests[0]
        assert headers["Authorization"] == "Bearer env-token"

    def test_explicit_token_beats_env_var(self, monkeypatch):
        monkeypatch.setenv("BENCHER_API_TOKEN", "env-token")
        transport = FakeTransport()
        _load(transport=transport, bencher_token="option-token")
        _, headers = transport.requests[0]
        assert headers["Authorization"] == "Bearer option-token"

    def test_no_token_no_auth_header(self, monkeypatch):
        monkeypatch.delenv("BENCHER_API_TOKEN", raising=False)
        transport = FakeTransport()
        _load(transport=transport)
        _, headers = transport.requests[0]
        assert "Authorization" not in headers


class _StubHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/v0/projects/demo/reports":
            self.send_error(404)
            return
        self.server.seen_auth.append(self.headers.get("Authorization"))
        query = urllib.parse.parse_qs(parsed.query)
        page = int(query["page"][0])
        per_page = int(query["per_page"][0])
        chunk = REPORTS[(page - 1) * per_page : page * per_page]
        body = json.dumps(chunk).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TestHttpServerStub:
    def test_fetch_against_local_stub(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
        server.seen_auth = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}"
            dataset = BencherApiInputFormat().load(
                None,
                {
                    "project": "demo",
                    "bencher_url": url,
                    "bencher_project": "demo",
                    "bencher_token": "stub-token",
                },
            )
            assert [r.id for r in dataset.revisions] == [C1, C2]
            assert server.seen_auth[0] == "Bearer stub-token"
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


class TestCli:
    def test_build_without_input_dir(self, tmp_path, monkeypatch):
        plugin = plugins.input_formats.get("bencher-api")
        monkeypatch.setattr(plugin, "transport", FakeTransport())
        out_dir = tmp_path / "site"
        rc = main(
            [
                "build",
                "-i",
                "bencher-api",
                "--bencher-project",
                "demo",
                "-o",
                str(out_dir),
                "--project",
                "demo",
            ]
        )
        assert rc == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert index["params"]["testbed"] == ["linux-x64", "macos-arm"]
