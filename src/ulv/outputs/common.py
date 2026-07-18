"""Shared site-build pipeline for the HTML output generators.

Both generators emit the same data contract — `graphs/**/*.json`,
`index.json`, `info.json` — mirroring asv's publish step
(publish.py:283-310), and both build atomically. Everything here is
frontend-agnostic; each generator supplies only its static assets and
page rendering.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import time
from pathlib import Path

from ulv import __version__
from ulv.model import Benchmark, Dataset
from ulv.outputs.html.graphs import (
    GraphSet,
    get_weight,
    is_na,
    make_summary_graph,
)
from ulv.outputs.html.paths import graph_path, sanitize_filename

PAGES = [
    # [name, button_label, description] per asv's OutputPublisher
    # registrations (summarygrid.py:7-10, summarylist.py:31-33);
    # the Regressions page is dropped (spec Decision 6).
    ["", "Grid view", "Display as a agrid"],
    ["summarylist", "List view", "Display as a list"],
]

HASH_LENGTH = 8


def _js_timestamp(moment) -> int:
    return int(moment.timestamp() * 1000)


def benchmark_param_iter(benchmark: Benchmark):
    """(flat index, param-value tuple) per combination, or (None, ()) for
    a non-parameterized benchmark (summarylist.py:11-27)."""
    if not benchmark.params:
        yield None, ()
    else:
        yield from enumerate(itertools.product(*benchmark.params))


def atomic_site_build(out_dir: Path, populate) -> None:
    """Build a site via `populate(build_dir)` and swap it into place.

    Output is atomic: the site is built in a temp directory next to the
    target and swapped in only on success, so a failed build never
    leaves a partially broken site. Directory renames bound that
    guarantee: a hard kill between the two renames can leave the
    previous site parked under the hidden `.<name>.old-<pid>` name
    rather than at the target path; both hidden names are pre-cleaned
    on the next run.
    """
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    build_dir = out_dir.parent / f".{out_dir.name}.build-{os.getpid()}"
    old_dir = out_dir.parent / f".{out_dir.name}.old-{os.getpid()}"
    shutil.rmtree(build_dir, ignore_errors=True)
    shutil.rmtree(old_dir, ignore_errors=True)

    try:
        populate(build_dir)
    except BaseException:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise

    # Swap: the previous site stays valid until the rename, and is
    # restored if the build directory cannot take its place.
    if out_dir.exists():
        out_dir.rename(old_dir)
    try:
        build_dir.rename(out_dir)
    except BaseException:
        if old_dir.exists():
            old_dir.rename(out_dir)
        shutil.rmtree(build_dir, ignore_errors=True)
        raise
    shutil.rmtree(old_dir, ignore_errors=True)


def build_graphs(dataset: Dataset) -> tuple[GraphSet, dict]:
    """One graph per (benchmark × environment params × branch), as
    publish.py:203-236 builds them: env factors plus the revision's
    branch(es), missing params filled with None and None added to
    that axis' value set. A commit on several configured branches is
    graphed on each of them, like asv's result × containing-branch
    loop."""
    env_by_id = {env.id: env for env in dataset.environments}
    revision_index = {rev.id: i for i, rev in enumerate(dataset.revisions)}
    # publish coerces None param values to '' (publish.py:224-226);
    # an unknown branch gets the same spelling.
    branches_of = {
        rev.id: (rev.branches or (rev.branch or "",)) for rev in dataset.revisions
    }

    axis_values: dict[str, set] = {}
    for env in dataset.environments:
        for factor, value in env.factors.items():
            axis_values.setdefault(factor, set()).add(value)
    axis_values.setdefault("branch", set())
    for branches in branches_of.values():
        axis_values["branch"].update(branches)

    graph_set = GraphSet()
    for series in dataset.series:
        environment = env_by_id[series.environment]
        benchmark = dataset.benchmarks[series.benchmark]
        parameterized = bool(benchmark.params)
        for revision_id, point in series.points.items():
            if parameterized:
                value = list(point.value)
                if isinstance(point.stats, (list, tuple)):
                    weight = [get_weight(s) for s in point.stats]
                else:
                    weight = [None] * len(value)
            else:
                value = point.value
                weight = get_weight(point.stats)

            for branch in branches_of[revision_id]:
                cur_params = dict(environment.factors)
                cur_params["branch"] = branch
                for key in axis_values:
                    if key not in cur_params:
                        cur_params[key] = None
                        axis_values[key].add(None)

                graph = graph_set.get_graph(benchmark.name, cur_params)
                graph.add_data_point(revision_index[revision_id], value, weight)
    return graph_set, axis_values


def write_summarylist(build_dir: Path, dataset: Dataset, graph_set: GraphSet) -> None:
    """Per-environment summary.json rows (summarylist.py:36-114).
    Step detection is skipped (spec Decision 6): last_value comes from
    the raw series tail, last_err is the tail point's ci_99 width
    recovered from its weight (weight = 2/width), and the change
    columns stay null. When several runs at one revision were
    averaged, weights average arithmetically, so the recovered
    width is the harmonic mean of the runs' ci widths — not any
    single run's width."""
    results: dict[str, list] = {}
    for benchmark_name, benchmark in sorted(dataset.benchmarks.items()):
        graphs = graph_set.get_graph_group(benchmark_name)
        data_by_path = {graph.path: graph.get_data() for graph in graphs}
        for idx, benchmark_param in benchmark_param_iter(benchmark):
            pretty_name = benchmark.pretty_name or benchmark_name
            if idx is not None:
                pretty_name = f"{pretty_name}({', '.join(benchmark_param)})"
            for graph in graphs:
                last_rev = None
                last_value = None
                last_err = None
                for revision, value, weight in data_by_path[graph.path]:
                    if idx is not None:
                        weight = weight[idx] if weight else None
                        value = value[idx]
                    if not is_na(value):
                        last_rev = revision
                        last_value = value
                        last_err = 2 / weight if not is_na(weight) else None
                row = {
                    "name": benchmark_name,
                    "idx": idx,
                    "pretty_name": pretty_name,
                    "last_rev": last_rev,
                    "last_value": last_value,
                    "last_err": last_err,
                    "prev_value": None,
                    "change_rev": None,
                }
                path = graph_path(graph.params, "summary") + ".json"
                results.setdefault(path, []).append(row)

    for path, rows in results.items():
        target = build_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        rows.sort(key=lambda row: (row["name"], row["idx"] or 0))
        target.write_text(json.dumps(rows, separators=(",", ":"), allow_nan=False))


def index_data(
    dataset: Dataset, options, graph_set: GraphSet, axis_values: dict
) -> dict:
    revision_to_hash = {}
    revision_to_date = {}
    for i, revision in enumerate(dataset.revisions):
        revision_to_hash[i] = revision.commit_hash
        if revision.date is not None:
            revision_to_date[i] = _js_timestamp(revision.date)

    params = {}
    for key, values in axis_values.items():
        # asv's axis ordering: None sorts as the string '[none]'
        # (publish.py:277-280).
        params[key] = sorted(values, key=lambda x: "[none]" if x is None else str(x))

    graph_param_list = graph_set.param_list()

    # Additive path manifest: any graph file is dir + "/" + stem +
    # ".json", so a frontend never recomputes sanitized paths
    # client-side. `dirs` is a parallel array rather than a key
    # inside each graph_param_list entry because the vendored
    # frontend's graph_to_path iterates entry keys to build paths.
    # Deriving dirs and stems from graph_path/sanitize_filename —
    # the same functions that place the files — keeps the manifest
    # and the on-disk layout from drifting apart.
    def graph_dir(params: dict) -> str:
        return graph_path(params, "x").rsplit("/", 1)[0]

    graph_paths = {
        "dirs": [graph_dir(entry) for entry in graph_param_list],
        "summary_dir": graph_dir({"summary": ""}),
        "benchmarks": {name: sanitize_filename(name) for name in dataset.benchmarks},
    }

    benchmarks = {}
    for name, benchmark in dataset.benchmarks.items():
        entry = dict(benchmark.extra)
        entry["name"] = benchmark.name
        entry["param_names"] = list(benchmark.param_names)
        entry["params"] = [list(axis) for axis in benchmark.params]
        if benchmark.unit is not None:
            entry["unit"] = benchmark.unit
        if benchmark.type is not None:
            entry["type"] = benchmark.type
        if benchmark.pretty_name is not None:
            entry["pretty_name"] = benchmark.pretty_name
        benchmarks[name] = entry

    machines = {}
    for environment in dataset.environments:
        info = environment.extra.get("machine_info")
        machine = environment.factors.get("machine")
        if machine and isinstance(info, dict):
            machines[machine] = info

    tags = {}
    for i, revision in enumerate(dataset.revisions):
        for tag in revision.tags:
            tags[tag] = i

    return {
        "project": dataset.project,
        "project_url": options.get("project_url", "#"),
        "show_commit_url": options.get("show_commit_url", ""),
        "hash_length": HASH_LENGTH,
        "revision_to_hash": revision_to_hash,
        "revision_to_date": revision_to_date,
        "params": params,
        "graph_param_list": graph_param_list,
        "graph_paths": graph_paths,
        "benchmarks": benchmarks,
        "machines": machines,
        "tags": tags,
        "pages": PAGES,
    }


def write_site_data(build_dir: Path, dataset: Dataset, options) -> None:
    """Emit the shared data files for a time-axis dataset: graph JSON,
    per-benchmark summary graphs, per-environment summary rows,
    `index.json` (compact, sorted keys) and `info.json`."""
    graph_set, axis_values = build_graphs(dataset)
    graph_set.save(build_dir)
    for name in graph_set.benchmark_names():
        make_summary_graph(graph_set.get_graph_group(name)).save(build_dir)
    write_summarylist(build_dir, dataset, graph_set)

    index = index_data(dataset, options, graph_set, axis_values)
    (build_dir / "index.json").write_text(
        json.dumps(index, sort_keys=True, separators=(",", ":"))
    )
    info = {
        "asv-version": f"ulv {__version__}",
        "timestamp": int(time.time() * 1000),
    }
    (build_dir / "info.json").write_text(json.dumps(info))


def snapshot_table(dataset: Dataset) -> tuple[list[str], list[list[str]]]:
    """Header labels and cell rows for a snapshot (no-time-axis)
    dataset: one row per benchmark × measure (× testbed), values and
    bounds as plain strings, absent bounds as empty strings — never
    zero. Cells are unescaped; HTML rendering is the caller's job."""
    environments = {env.id: env for env in dataset.environments}
    show_testbed = any(env.factors for env in dataset.environments)

    def cell(value) -> str:
        return "" if value is None else str(value)

    rows = []
    for name in sorted(dataset.benchmarks):
        benchmark = dataset.benchmarks[name]
        bench_label = benchmark.extra.get("bmf_benchmark", benchmark.name)
        measure_label = benchmark.extra.get("bmf_measure", benchmark.unit or "")
        for series in dataset.series_for(name):
            point = next(iter(series.points.values()), None)
            if point is None:
                continue
            cells = [cell(bench_label), cell(measure_label)]
            if show_testbed:
                factors = environments[series.environment].factors
                cells.append(cell(factors.get("testbed", "")))
            cells += [cell(point.value), cell(point.lower), cell(point.upper)]
            rows.append(cells)

    headers = ["Benchmark", "Measure"]
    if show_testbed:
        headers.append("Testbed")
    headers += ["Value", "Lower bound", "Upper bound"]
    return headers, rows


def snapshot_commit(dataset: Dataset) -> tuple[str, str] | None:
    """(commit hash, ISO date or "") of the lone snapshot revision, or
    None when there is no revision or no hash to show."""
    revision = dataset.revisions[0] if dataset.revisions else None
    if revision is None or not revision.commit_hash:
        return None
    when = revision.date.isoformat() if revision.date else ""
    return revision.commit_hash, when
