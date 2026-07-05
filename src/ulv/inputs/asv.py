"""ASV native results reader.

Reads an ASV results directory (`<machine>/machine.json`, shared
`benchmarks.json`, per-commit `<hash8>-<env>.json` files) into a
`Dataset`, mirroring the read side of asv's `results.py` / `machine.py`
for api_version 2 result files. Without a git repository, revisions are
ordered by the `date` recorded in the result files (git enrichment is a
separate, optional step).
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
from pathlib import Path

from ulv.errors import UlvError
from ulv.model import (
    Benchmark,
    Dataset,
    Environment,
    ResultPoint,
    ResultSeries,
    Revision,
)

RESULT_API_VERSION = 2
BENCHMARKS_API_VERSION = 2
MACHINE_API_VERSION = 1

# Benchmark entry fields consumed into Benchmark attributes; the rest go
# to Benchmark.extra so nothing in benchmarks.json is dropped.
_BENCHMARK_FIELDS = {"name", "unit", "type", "param_names", "params", "pretty_name"}

# result_columns handled per asv/results.py load(); anything else in a
# result file is an error there and here.
_SIMPLE_COLUMNS = {
    "result",
    "params",
    "version",
    "started_at",
    "duration",
    "samples",
    "profile",
}
_POINT_EXTRA_COLUMNS = ("started_at", "duration", "samples", "profile")


def _load_json(path: Path) -> dict:
    try:
        text = path.read_text()
    except OSError as exc:
        raise UlvError(f"cannot read {path}: {exc}", offending_input=str(path)) from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise UlvError(
            f"malformed JSON in {path}: {exc}", offending_input=str(path)
        ) from exc
    if not isinstance(data, dict):
        raise UlvError(f"expected a JSON object in {path}", offending_input=str(path))
    return data


def _check_api_version(data: dict, expected: int, path: Path) -> None:
    version = data.get("version")
    if version == expected:
        return
    if version is None:
        raise UlvError(f"{path} has no api_version marker", offending_input=str(path))
    if isinstance(version, int) and version < expected:
        raise UlvError(
            f"{path} uses api_version {version}; only api_version {expected} "
            f"is supported — upgrade the data with `asv update`",
            offending_input=str(path),
        )
    raise UlvError(
        f"{path} uses api_version {version}, newer than the supported "
        f"api_version {expected}",
        offending_input=str(path),
    )


def _compatible_results(result, result_params, params):
    """Positional remap of stored values onto the current parameter axes,
    as asv/results.py:_compatible_results does. `None` result means every
    combination failed (e.g. build failure)."""
    if result is None:
        return [None for _ in itertools.product(*params)]
    stored = dict(zip((tuple(p) for p in itertools.product(*result_params)), result))
    return [stored.get(tuple(p)) for p in itertools.product(*params)]


def _decode_row(columns: list, row: list, path: Path) -> dict:
    """One benchmark's row -> cell dict, reassembling `stats_*` columns
    into per-combination stats mappings."""
    cells: dict[str, object] = dict.fromkeys(_SIMPLE_COLUMNS)
    stats: list[dict] | None = None
    for column, value in zip(columns, row):
        if column in _SIMPLE_COLUMNS:
            cells[column] = value
        elif column.startswith("stats_"):
            if value is not None:
                if stats is None:
                    stats = [{} for _ in value]
                for index, item in enumerate(value):
                    if item is not None:
                        stats[index][column[6:]] = item
        else:
            raise UlvError(
                f"unknown result column {column!r} in {path}",
                offending_input=str(path),
            )
    cells["stats"] = stats
    return cells


def _point_from_cells(cells: dict, benchmark: Benchmark) -> ResultPoint:
    result = cells["result"]
    stored_params = cells["params"] or []
    stats = cells["stats"]

    if benchmark.params:
        params = [list(axis) for axis in benchmark.params]
        if stored_params and [list(p) for p in stored_params] != params:
            values = _compatible_results(result, stored_params, params)
            stats = None  # stats indices no longer line up after remapping
        elif result is None:
            values = [None for _ in itertools.product(*params)]
        else:
            values = list(result)
        value: object = tuple(values)
        point_stats = tuple(dict(s) if s else None for s in stats) if stats else None
    else:
        value = result[0] if isinstance(result, list) else result
        point_stats = stats[0] if stats else None

    extra = {key: cells[key] for key in _POINT_EXTRA_COLUMNS if cells[key] is not None}
    return ResultPoint(value=value, stats=point_stats, extra=extra)


def _load_benchmarks(path: Path) -> dict[str, Benchmark]:
    data = _load_json(path)
    _check_api_version(data, BENCHMARKS_API_VERSION, path)
    benchmarks = {}
    for name, entry in data.items():
        if name == "version":
            continue
        if not isinstance(entry, dict):
            raise UlvError(
                f"benchmark entry {name!r} in {path} is not an object",
                offending_input=str(path),
            )
        benchmarks[name] = Benchmark(
            name=name,
            unit=entry.get("unit"),
            type=entry.get("type"),
            param_names=tuple(entry.get("param_names") or ()),
            params=tuple(tuple(axis) for axis in entry.get("params") or ()),
            pretty_name=entry.get("pretty_name"),
            extra={k: v for k, v in entry.items() if k not in _BENCHMARK_FIELDS},
        )
    return benchmarks


def _load_machine(path: Path) -> dict:
    info = _load_json(path)
    _check_api_version(info, MACHINE_API_VERSION, path)
    if not isinstance(info.get("machine"), str):
        raise UlvError(f"{path} has no string 'machine' key", offending_input=str(path))
    return {key: value for key, value in info.items() if key != "version"}


def _env_factors(result: dict) -> dict[str, str]:
    """Env params + env vars -> filter-axis factors, as asv's publish
    collects them: None becomes '' and env vars get an 'env-' prefix."""
    factors = {}
    for key, value in result["params"].items():
        factors[key] = "" if value is None else str(value)
    for key, value in result.get("env_vars", {}).items():
        factors[f"env-{key}"] = "" if value is None else str(value)
    return factors


class AsvInputFormat:
    """Built-in `asv` input format (results directory, no git required)."""

    name = "asv"

    def load(self, source, options) -> Dataset:
        source = Path(source)
        if not source.is_dir():
            raise UlvError(
                f"ASV results directory not found: {source}",
                offending_input=str(source),
            )

        benchmarks = _load_benchmarks(source / "benchmarks.json")

        environments: dict[str, dict] = {}
        points: dict[tuple[str, str], dict[str, ResultPoint]] = {}
        revision_dates: dict[str, int] = {}

        for machine_dir in sorted(p for p in source.iterdir() if p.is_dir()):
            result_files = sorted(
                p for p in machine_dir.glob("*.json") if p.name != "machine.json"
            )
            machine_path = machine_dir / "machine.json"
            if not machine_path.is_file():
                if result_files:
                    raise UlvError(
                        f"{machine_dir} contains result files but no machine.json",
                        offending_input=str(machine_path),
                    )
                continue
            machine_info = _load_machine(machine_path)

            for result_file in result_files:
                self._load_result_file(
                    result_file,
                    machine_info,
                    benchmarks,
                    environments,
                    points,
                    revision_dates,
                )

        if not environments:
            raise UlvError(
                f"no ASV machine directories with results found in {source}",
                offending_input=str(source),
            )

        revisions = tuple(
            Revision(
                id=commit,
                commit_hash=commit,
                date=dt.datetime.fromtimestamp(date / 1000, tz=dt.UTC),
            )
            for commit, date in sorted(
                revision_dates.items(), key=lambda item: (item[1], item[0])
            )
        )
        environment_objs = tuple(
            Environment(id=env_id, factors=env["factors"], extra=env["extra"])
            for env_id, env in sorted(environments.items())
        )
        series = tuple(
            ResultSeries(benchmark=bench, environment=env_id, points=pts)
            for (bench, env_id), pts in sorted(points.items())
        )
        return Dataset(
            project=options.get("project", "") if options else "",
            revisions=revisions,
            environments=environment_objs,
            benchmarks=benchmarks,
            series=series,
        )

    def _load_result_file(
        self,
        path: Path,
        machine_info: dict,
        benchmarks: dict[str, Benchmark],
        environments: dict[str, dict],
        points: dict[tuple[str, str], dict[str, ResultPoint]],
        revision_dates: dict[str, int],
    ) -> None:
        data = _load_json(path)
        _check_api_version(data, RESULT_API_VERSION, path)

        try:
            commit = data["commit_hash"]
            date = data["date"]
            env_name = data["env_name"]
            columns = data["result_columns"]
            results = data["results"]
            _ = data["params"]
        except KeyError as exc:
            raise UlvError(
                f"missing key {exc} in result file {path}",
                offending_input=str(path),
            ) from exc

        revision_dates[commit] = min(revision_dates.get(commit, date), date)

        env_id = f"{machine_info['machine']}/{env_name}"
        env = environments.setdefault(
            env_id,
            {
                "factors": _env_factors(data),
                "extra": {
                    "env_name": env_name,
                    "machine_info": machine_info,
                    "durations": {},
                },
            },
        )
        durations = data.get("durations") or {}
        if durations:
            env["extra"]["durations"][commit] = durations

        for name, row in results.items():
            benchmark = benchmarks.get(name)
            if benchmark is None:
                continue
            cells = _decode_row(columns, row, path)
            stored_version = cells["version"]
            expected_version = benchmark.extra.get("version")
            if (
                stored_version is not None
                and expected_version is not None
                and stored_version != expected_version
            ):
                continue
            points.setdefault((name, env_id), {})[commit] = _point_from_cells(
                cells, benchmark
            )
