"""Static HTML site generator using the vendored ASV frontend.

Mirrors the output contract of asv's publish step (publish.py:283-310):
the vendored frontend boots from `info.json`, then `index.json`, then
fetches graph JSON files by recomputing paths client-side. Output is
atomic: the site is built in a temp directory next to the target and
swapped in only on success, so a failed build never leaves a partially
broken site.
"""

from __future__ import annotations

import importlib.resources
import json
import os
import shutil
import time
from pathlib import Path

from ulv import __version__
from ulv.model import Dataset

_PAGES = [
    # [name, button_label, description] per asv's OutputPublisher
    # registrations (summarygrid.py:7-10, summarylist.py:31-33);
    # the Regressions page is dropped (spec Decision 6).
    ["", "Grid view", "Display as a agrid"],
    ["summarylist", "List view", "Display as a list"],
]

_HASH_LENGTH = 8


def _js_timestamp(moment) -> int:
    return int(moment.timestamp() * 1000)


class HtmlOutputGenerator:
    """Built-in `html` output generator."""

    name = "html"

    def generate(self, dataset: Dataset, out_dir, options) -> None:
        out_dir = Path(out_dir)
        options = options or {}
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        build_dir = out_dir.parent / f".{out_dir.name}.build-{os.getpid()}"
        old_dir = out_dir.parent / f".{out_dir.name}.old-{os.getpid()}"
        shutil.rmtree(build_dir, ignore_errors=True)

        try:
            self._copy_static(build_dir)
            (build_dir / "graphs").mkdir(exist_ok=True)
            self._write_site_json(build_dir, dataset, options)
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

    def _copy_static(self, build_dir: Path) -> None:
        static_root = importlib.resources.files("ulv.outputs.html") / "static"
        with importlib.resources.as_file(static_root) as static_path:
            shutil.copytree(static_path, build_dir)

    def _write_site_json(self, build_dir: Path, dataset: Dataset, options) -> None:
        index = self._index_data(dataset, options)
        (build_dir / "index.json").write_text(json.dumps(index, sort_keys=True))
        info = {
            "asv-version": f"ulv {__version__}",
            "timestamp": int(time.time() * 1000),
        }
        (build_dir / "info.json").write_text(json.dumps(info))

    def _index_data(self, dataset: Dataset, options) -> dict:
        revision_to_hash = {}
        revision_to_date = {}
        for i, revision in enumerate(dataset.revisions):
            revision_to_hash[i] = revision.commit_hash
            if revision.date is not None:
                revision_to_date[i] = _js_timestamp(revision.date)

        # Without repository info every revision carries branch None;
        # the axis still exists because the frontend and the graph path
        # scheme treat 'branch' as a regular (single-select) parameter.
        branches = sorted(
            {revision.branch for revision in dataset.revisions},
            key=lambda b: (b is not None, b),
        ) or [None]
        params = {
            factor: list(values)
            for factor, values in dataset.environment_axes().items()
        }
        params["branch"] = branches

        graph_param_list = []
        for environment in dataset.environments:
            for branch in branches:
                entry = dict(environment.factors)
                entry["branch"] = branch
                if entry not in graph_param_list:
                    graph_param_list.append(entry)

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

        return {
            "project": dataset.project,
            "project_url": options.get("project_url", "#"),
            "show_commit_url": options.get("show_commit_url", ""),
            "hash_length": _HASH_LENGTH,
            "revision_to_hash": revision_to_hash,
            "revision_to_date": revision_to_date,
            "params": params,
            "graph_param_list": graph_param_list,
            "benchmarks": benchmarks,
            "machines": machines,
            "tags": {},
            "pages": _PAGES,
        }
