"""Bencher REST API reader (spec Decision 1; ADR 0005).

Fetches a project's reports read-only from a Bencher server
(`GET /v0/projects/{project}/reports`, paginated) and maps them onto
the same model shapes as the BMF input: each (benchmark, measure)
becomes an internal benchmark `<bench> (<measure-slug>)`, metric
bounds land on the point, and the testbed becomes one opaque
environment factor that user-supplied decomposition replaces. API
metadata stands in for BMF's sidecar files: `branch.head.version.hash`
is the commit, `start_time` the revision date, the branch name the
branch. Response shape modeled on Bencher's OpenAPI document, API
version 0.6.8 (see tests/fixtures/bencher_api/README.md).

The API token travels only in the Authorization header and is
scrubbed from every error message this module raises.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from ulv.errors import UlvError
from ulv.model import (
    Benchmark,
    Dataset,
    Environment,
    ResultPoint,
    ResultSeries,
    Revision,
)
from ulv.testbeds import resolve_testbeds

DEFAULT_URL = "https://api.bencher.dev"

PER_PAGE = 100

# Refusing to page forever turns a server that ignores pagination
# parameters into a diagnosable error instead of an endless loop.
MAX_PAGES = 10_000


class UrllibTransport:
    """Default transport: one authenticated GET per call."""

    def get(self, url: str, headers: dict) -> tuple[int, bytes]:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            raise UlvError(
                f"cannot reach {url}: {exc.reason}", offending_input=url
            ) from None


class BencherApiInputFormat:
    """Built-in `bencher-api` input format."""

    name = "bencher-api"

    def __init__(self, transport=None):
        self.transport = transport

    def load(self, source, options) -> Dataset:
        options = options or {}
        token = options.get("bencher_token") or os.environ.get("BENCHER_API_TOKEN")
        try:
            return self._load(options, token)
        except UlvError as exc:
            raise _scrubbed(exc, token) from None

    def _load(self, options: dict, token: str | None) -> Dataset:
        base = (options.get("bencher_url") or DEFAULT_URL).rstrip("/")
        project = options.get("bencher_project")
        if not project:
            raise UlvError(
                "the bencher-api input needs a project: pass "
                "--bencher-project or set 'bencher_project' in the config"
            )
        transport = options.get("transport") or self.transport or UrllibTransport()

        reports = _fetch_reports(transport, base, project, token)
        return self._dataset(reports, base, project, options)

    def _dataset(
        self, reports: list, base: str, project: str, options: dict
    ) -> Dataset:
        endpoint = _reports_url(base, project, 1)
        parsed = []
        for report in reports:
            try:
                parsed.append(_parse_report(report))
            except (KeyError, TypeError, AttributeError) as exc:
                raise UlvError(
                    f"malformed report payload from {endpoint}: {exc!r}",
                    offending_input=endpoint,
                ) from None

        testbed_config = options.get("testbeds")
        factors_by_testbed = None
        if testbed_config is not None:
            names = {testbed for _, testbed, _ in parsed}
            factors_by_testbed = resolve_testbeds(
                names, testbed_config, bool(options.get("allow_unmapped"))
            )

        revisions: dict[str, Revision] = {}
        environments: dict[str, Environment] = {}
        benchmarks: dict[str, Benchmark] = {}
        series_points: dict[tuple[str, str], dict[str, ResultPoint]] = {}

        for revision, testbed, points in parsed:
            existing = revisions.get(revision.id)
            if existing is None:
                revisions[revision.id] = revision
            elif revision.date and existing.date and revision.date < existing.date:
                # Reports for one version run at different times per
                # testbed; the revision keeps the earliest start.
                revisions[revision.id] = revision

            if testbed not in environments:
                if factors_by_testbed is not None:
                    environments[testbed] = Environment(
                        id=testbed,
                        factors=factors_by_testbed[testbed],
                        extra={"testbed": testbed},
                    )
                else:
                    environments[testbed] = Environment(
                        id=testbed, factors={"testbed": testbed}
                    )

            for (bench, measure), point in points.items():
                name = f"{bench} ({measure})"
                if name not in benchmarks:
                    benchmarks[name] = Benchmark(
                        name=name,
                        unit=measure,
                        pretty_name=name,
                        extra={"bmf_benchmark": bench, "bmf_measure": measure},
                    )
                series_points.setdefault((name, testbed), {}).setdefault(
                    revision.id, point
                )

        ordered = sorted(
            revisions.values(),
            key=lambda r: (r.date or dt.datetime.fromtimestamp(0, tz=dt.UTC), r.id),
        )
        return Dataset(
            project=options.get("project", ""),
            revisions=tuple(ordered),
            environments=tuple(environments[eid] for eid in sorted(environments)),
            benchmarks=benchmarks,
            series=tuple(
                ResultSeries(benchmark=bench, environment=env_id, points=pts)
                for (bench, env_id), pts in sorted(series_points.items())
            ),
        )


def _reports_url(base: str, project: str, page: int) -> str:
    return (
        f"{base}/v0/projects/{urllib.parse.quote(project)}/reports"
        f"?per_page={PER_PAGE}&page={page}"
    )


def _fetch_reports(transport, base: str, project: str, token: str | None) -> list:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    reports: list = []
    for page in range(1, MAX_PAGES + 1):
        url = _reports_url(base, project, page)
        status, body = transport.get(url, headers)
        if status in (401, 403):
            raise UlvError(
                f"authentication failed (HTTP {status}) for {url}; check "
                f"the API token (--bencher-token, 'bencher_token', or "
                f"BENCHER_API_TOKEN)",
                offending_input=url,
            )
        if status != 200:
            raise UlvError(f"HTTP {status} from {url}", offending_input=url)
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise UlvError(
                f"malformed JSON from {url}: {exc}", offending_input=url
            ) from None
        if not isinstance(data, list):
            raise UlvError(
                f"unexpected payload from {url}: expected a JSON array of reports",
                offending_input=url,
            )
        reports.extend(data)
        if len(data) < PER_PAGE:
            return reports
    raise UlvError(
        f"pagination never terminated after {MAX_PAGES} pages of "
        f"{_reports_url(base, project, 1)}",
        offending_input=_reports_url(base, project, MAX_PAGES),
    )


def _parse_report(report: dict):
    """One JsonReport -> (Revision, testbed name, {(bench, measure): point})."""
    branch = report["branch"]
    branch_name = branch["name"]
    version = (branch.get("head") or {}).get("version") or {}
    commit = version.get("hash")
    number = version.get("number")
    if commit:
        revision_id = commit
    elif number is not None:
        revision_id = f"{branch_name}/v{number}"
    else:
        revision_id = report["uuid"]

    date = dt.datetime.fromisoformat(report["start_time"])
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.UTC)
    revision = Revision(
        id=revision_id,
        commit_hash=commit,
        date=date.astimezone(dt.UTC),
        branch=branch_name,
    )

    testbed = report["testbed"].get("slug") or report["testbed"]["name"]

    points: dict[tuple[str, str], ResultPoint] = {}
    for iteration in report.get("results") or []:
        for result in iteration:
            bench = result["benchmark"]["name"]
            for entry in result.get("measures") or []:
                measure = entry["measure"]["slug"]
                metric = entry["metric"]
                # first iteration wins; repeats of a benchmark within
                # one report are ignored
                points.setdefault(
                    (bench, measure),
                    ResultPoint(
                        value=metric["value"],
                        lower=metric.get("lower_value"),
                        upper=metric.get("upper_value"),
                    ),
                )
    return revision, testbed, points


def _scrubbed(exc: UlvError, token: str | None) -> UlvError:
    """Defense in depth: even if a message somehow embeds the token
    (e.g. echoed by a server), it never leaves this module."""
    if not token:
        return exc
    message = exc.message.replace(token, "[token]")
    offending = exc.offending_input
    if isinstance(offending, str):
        offending = offending.replace(token, "[token]")
    return UlvError(message, offending_input=offending)
