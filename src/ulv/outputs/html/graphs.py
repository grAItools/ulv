"""Graph data generation, ported from asv/graph.py (BSD-3, see
LICENSES/asv.txt) minus step detection (spec Decision 6).

Semantics kept bit-for-bit with the upstream publish pipeline: values
for the same revision are arithmetic-averaged element-wise with
None/NaN treated as missing, revisions sort ascending, all-missing
revisions are trimmed from both edges, scalar series unwrap, and the
saved JSON is compact `[[revision, value], …]` with weights dropped.
Emitted files contain `null`, never `NaN` — every value passes through
`mean_na`, which maps all-missing to None.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ulv.outputs.html.paths import graph_path

# Upstream cap for summary-graph resampling (asv/graph.py:15): pixels
# across a Retina display, divided by 5 summaries and by 2 for line
# width.
RESAMPLED_POINTS = 3840 / 5 / 2


def is_na(value) -> bool:
    """True when value is None or NaN (asv/util.py:999-1012)."""
    return value is None or (isinstance(value, float) and value != value)


def mean_na(values):
    """Arithmetic mean ignoring None/NaN; None when nothing remains."""
    values = [x for x in values if not is_na(x)]
    if values:
        return sum(values) / len(values)
    return None


def geom_mean_na(values):
    """Sign-aware geometric mean ignoring None/NaN (asv/util.py:1027-1042)."""
    values = [x for x in values if not is_na(x)]
    if values:
        exponent = 1 / len(values)
        product = 1.0
        total = 0
        for x in values:
            product *= abs(x) ** exponent
            total += x
        return product if total >= 0 else -product
    return None


def get_weight(stats):
    """Data-point weight 2/|ci_99_b - ci_99_a| (asv/_stats.py:9-27)."""
    if stats is None or "ci_99_a" not in stats or "ci_99_b" not in stats:
        return None
    try:
        a = stats["ci_99_a"]
        b = stats["ci_99_b"]
        if math.isinf(a) or math.isinf(b):
            return None
        return 2 / abs(b - a)
    except ZeroDivisionError:
        return None


class Graph:
    """One frontend plot line: data points for a single benchmark under
    a single parameter (environment × branch) combination."""

    def __init__(self, benchmark_name: str, params: dict):
        self.benchmark_name = benchmark_name
        self.params = params
        self.data_points: dict[int, list] = {}
        self.data_weights: dict[int, list] = {}
        self.path = graph_path(params, benchmark_name)
        self.n_series: int | None = None
        self.scalar_series = True

    def add_data_point(self, revision: int, value, weight=None) -> None:
        self.data_points.setdefault(revision, [])
        self.data_weights.setdefault(revision, [])
        if not is_na(value):
            if not hasattr(value, "__len__"):
                value = [value]
                weight = [weight]
            else:
                self.scalar_series = False

            if self.n_series is None:
                self.n_series = len(value)
            elif len(value) != self.n_series:
                raise ValueError("Mismatching number of data series in graph")

            if weight is None:
                weight = [None] * len(value)

            self.data_points[revision].append(value)
            self.data_weights[revision].append(weight)

    def get_data(self) -> list:
        """Sorted `(revision, value, weight)` triples, duplicates averaged
        and all-missing edge revisions trimmed."""
        if self.n_series is None:
            self.n_series = 1

        def mean_axis0(rows):
            if not rows:
                return [None] * self.n_series
            return [mean_na(row[j] for row in rows) for j in range(self.n_series)]

        val = []
        for revision in self.data_points:
            val.append(
                (
                    revision,
                    mean_axis0(self.data_points[revision]),
                    mean_axis0(self.data_weights[revision]),
                )
            )
        val.sort()

        i = 0
        for i in range(len(val)):
            if any(not is_na(v) for v in val[i][1]):
                break
        else:
            i = len(val)
        j = i
        for j in range(len(val) - 1, i, -1):
            if any(not is_na(v) for v in val[j][1]):
                break
        val = val[i : j + 1]

        if self.scalar_series:
            val = [(k, v[0], w[0]) for k, v, w in val]
        return val

    def save(self, html_dir: Path) -> None:
        filename = Path(html_dir) / (self.path + ".json")
        filename.parent.mkdir(parents=True, exist_ok=True)
        val = [v[:2] for v in self.get_data()]
        filename.write_text(json.dumps(val, separators=(",", ":"), allow_nan=False))


class GraphSet:
    """All graphs of one site build, keyed by path, grouped by benchmark."""

    def __init__(self):
        self._graphs: dict[str, Graph] = {}
        self._groups: dict[str, list[Graph]] = {}

    def get_graph(self, benchmark_name: str, params: dict) -> Graph:
        graph = Graph(benchmark_name, params)
        if graph.path not in self._graphs:
            self._graphs[graph.path] = graph
            self._groups.setdefault(benchmark_name, []).append(graph)
        return self._graphs[graph.path]

    def get_graph_group(self, benchmark_name: str) -> list[Graph]:
        return self._groups.get(benchmark_name, [])

    def benchmark_names(self) -> list[str]:
        return list(self._groups)

    def param_list(self) -> list[dict]:
        """Distinct non-summary graph params — what the frontend permutes
        to find graph files (publish.py:238-243)."""
        result = []
        for graph in self._graphs.values():
            if "summary" not in graph.params and graph.params not in result:
                result.append(graph.params)
        return result

    def save(self, html_dir: Path) -> None:
        for graph in self._graphs.values():
            graph.save(html_dir)

    def __iter__(self):
        return iter(self._graphs.items())

    def __len__(self):
        return len(self._graphs)


def make_summary_graph(graphs: list[Graph]) -> Graph:
    x, ys = _combine_graph_data(graphs)
    y = _compute_summary_data_series(*ys)
    val = resample_data(list(zip(x, y)))
    graph = Graph(graphs[0].benchmark_name, {"summary": ""})
    for x_value, y_value in val:
        graph.add_data_point(x_value, y_value)
    return graph


def _compute_summary_data_series(*ys):
    """Per-x geometric mean across series, each series gap-filled first;
    x-values missing from every original series stay missing."""
    filled = [_fill_missing_data(y) for y in ys]
    res = []
    for i in range(len(ys[0])):
        if any(not is_na(y[i]) for y in ys):
            v = geom_mean_na(y[i] for y in filled)
        else:
            v = None
        res.append(v)
    return res


def _fill_missing_data(y, max_gap_fraction=0.1):
    """Linear interpolation inside gaps no larger than `max_gap_fraction`
    of the series' valid points."""
    valid_count = sum(int(not is_na(v)) for v in y)
    max_gap_size = math.ceil(max_gap_fraction * valid_count)

    filled = list(y)
    prev = None
    prev_idx = 0
    for i, v in enumerate(y):
        if not is_na(v):
            gap_size = i - prev_idx - 1
            if 0 < gap_size <= max_gap_size and not is_na(prev):
                for k in range(1, gap_size + 1):
                    filled[prev_idx + k] = (v * k + (gap_size + 1 - k) * prev) / (
                        gap_size + 1
                    )
            prev = v
            prev_idx = i
    return filled


def _combine_graph_data(graphs: list[Graph]):
    """All graphs' series on a shared sorted x-grid, None where a graph
    has no data for an x-value."""
    datasets = [graph.get_data() for graph in graphs]
    n_series = sum(graph.n_series for graph in graphs)

    x = set()
    for dataset in datasets:
        x.update(k for k, _, _ in dataset)
    x = sorted(x)
    x_idx = dict(zip(x, range(len(x))))

    ys = [[None] * len(x_idx) for _ in range(n_series)]
    pos = 0
    for dataset, graph in zip(datasets, graphs):
        for k, v, _ in dataset:
            i = x_idx[k]
            if graph.scalar_series:
                v = [v]
            for j, y in enumerate(v):
                ys[pos + j][i] = y
        pos += graph.n_series
    return x, ys


def resample_data(val, num_points=RESAMPLED_POINTS):
    if len(val) < num_points:
        return val

    min_revision = min(x[0] for x in val)
    max_revision = max(x[0] for x in val)
    step_size = int((max_revision - min_revision) / num_points)
    if step_size == 0:
        step_size = max_revision - min_revision + 1

    new_val = []
    j = 0
    for i in range(min_revision + step_size, max_revision + step_size, step_size):
        chunk = []
        while j < len(val) and val[j][0] < i:
            chunk.append(val[j][1])
            j += 1
        if chunk:
            new_val.append((i, mean_na(chunk)))
    return new_val
