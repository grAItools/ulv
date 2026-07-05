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
from ulv.gitrepo import GitRepo
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
    samples = cells["samples"]

    if benchmark.params:
        params = [list(axis) for axis in benchmark.params]
        if [list(p) for p in stored_params] != params:
            # Values, stats and samples are positional — one slot per
            # parameter combination — so when the stored axes differ from
            # benchmarks.json all three go through the same remap
            # (asv/results.py:339-376). An empty stored axis list means a
            # formerly scalar benchmark: product(*[]) yields one () key,
            # so every current combination maps to None.
            values = _compatible_results(result, stored_params, params)
            if stats is not None:
                stats = _compatible_results(stats, stored_params, params)
            if samples is not None:
                samples = _compatible_results(samples, stored_params, params)
        elif result is None:
            values = [None for _ in itertools.product(*params)]
        else:
            values = list(result)
        value: object = tuple(values)
        if stats and any(s for s in stats):
            point_stats = tuple(dict(s) if s else None for s in stats)
        else:
            point_stats = None
        if samples is not None and all(s is None for s in samples):
            samples = None
    else:
        value = result[0] if isinstance(result, list) else result
        point_stats = stats[0] if stats else None

    cells = dict(cells, samples=samples)
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


def _merge_mapping(target: dict, incoming: dict, env_id: str, path: Path) -> None:
    """Union `incoming` into `target`; the same key reappearing with a
    different value within one environment means the data is inconsistent,
    which is reported rather than silently resolved."""
    for key, value in incoming.items():
        if key in target and target[key] != value:
            raise UlvError(
                f"conflicting values for {key!r} in environment {env_id!r}: "
                f"{target[key]!r} vs {value!r} in {path}",
                offending_input=str(path),
            )
        target[key] = value


def _git_revisions(
    repo_path, configured_branches: list[str], revision_dates: dict[str, int]
) -> tuple[Revision, ...]:
    """Repository-enriched revisions: rev-list topological order instead
    of result-date order, committer dates, tags, and attribution to every
    configured branch containing the commit (publish.py:169-236)."""
    repo = GitRepo(repo_path)
    branch_names = configured_branches or [repo.default_branch()]
    membership = {name: set(repo.branch_commits(name)) for name in branch_names}

    order = {commit: i for i, commit in enumerate(repo.rev_order())}
    for commit in revision_dates:
        if commit not in order:
            raise UlvError(
                f"result commit {commit} not found in repository {repo_path}",
                offending_input=commit,
            )

    tags_by_commit: dict[str, list[str]] = {}
    for tag, commit in repo.tags().items():
        tags_by_commit.setdefault(commit, []).append(tag)

    revisions = []
    for commit in sorted(revision_dates, key=order.__getitem__):
        branches = tuple(name for name in branch_names if commit in membership[name])
        revisions.append(
            Revision(
                id=commit,
                commit_hash=commit,
                date=dt.datetime.fromtimestamp(
                    repo.commit_date_ms(commit) / 1000, tz=dt.UTC
                ),
                branch=branches[0] if branches else None,
                branches=branches,
                tags=tuple(tags_by_commit.get(commit, ())),
            )
        )
    return tuple(revisions)


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

        options = options or {}
        repo_path = options.get("repo")
        configured_branches = list(options.get("branches") or [])
        if configured_branches and not repo_path:
            raise UlvError(
                "'branches' is configured but 'repo' is not; branch "
                "attribution needs the project's git repository"
            )
        if repo_path:
            revisions = _git_revisions(repo_path, configured_branches, revision_dates)
        else:
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
                "factors": {},
                "extra": {
                    "env_name": env_name,
                    "machine_info": machine_info,
                    "python": data.get("python"),
                    "requirements": {},
                    "durations": {},
                },
            },
        )
        # An environment usually spans several result files (one per
        # commit); each file contributes its params, like asv's publish
        # collects them per result (publish.py:143-149).
        _merge_mapping(env["factors"], _env_factors(data), env_id, path)
        # None and '' both mean "installed, no pinned version" (asv's
        # publish coerces None to '' for env params); normalize before
        # merging so the two spellings don't read as a conflict.
        requirements = {
            key: "" if value is None else value
            for key, value in (data.get("requirements") or {}).items()
        }
        _merge_mapping(env["extra"]["requirements"], requirements, env_id, path)
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
            # Excluded whenever the stored version differs from the
            # (possibly absent) benchmarks.json version, as asv does
            # (asv/results.py:308-316).
            if stored_version is not None and stored_version != expected_version:
                continue
            points.setdefault((name, env_id), {})[commit] = _point_from_cells(
                cells, benchmark
            )
