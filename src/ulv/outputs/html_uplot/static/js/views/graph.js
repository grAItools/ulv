// History-graph view. Selector panels are built generically from
// index.params — every axis is an ordinary axis — plus per-benchmark
// parameter sub-selection; one uPlot series is drawn per selected
// (environment entry × benchmark-param combination) permutation.
// All mutations write the URL hash; rendering starts from state.

import { fetchGraph, graphUrl } from "../data.js";
import { NONE, writeState } from "../state.js";

const PALETTE = [
  "#1a5fb4",
  "#c01c28",
  "#26a269",
  "#e66100",
  "#613583",
  "#63452c",
  "#0aa1dd",
  "#a51d2d",
];

let currentChart = null;
let currentWrap = null;

window.addEventListener(
  "resize",
  () => {
    if (currentChart && currentWrap) {
      currentChart.setSize({
        width: Math.max(currentWrap.clientWidth, 280),
        height: 380,
      });
    }
  },
  { passive: true },
);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function escapeHtml(text) {
  const span = document.createElement("span");
  span.textContent = text;
  return span.innerHTML;
}

function entryValue(entry, axis) {
  const value = entry[axis];
  return value === undefined ? null : value;
}

// Effective per-axis selections: hash values filtered to real ones,
// else every value — except branch, which defaults to its first value
// (the primary branch), matching the vendored frontend's default view.
export function axisSelections(index, state) {
  const selections = {};
  for (const [axis, values] of Object.entries(index.params)) {
    const chosen = (state.axes[axis] || []).filter((v) => values.includes(v));
    if (chosen.length) {
      selections[axis] = chosen;
    } else if (axis === "branch" && values.length > 1) {
      selections[axis] = [values[0]];
    } else {
      selections[axis] = values.slice();
    }
  }
  return selections;
}

function selectedEntryIndices(index, selections) {
  const chosen = [];
  index.graph_param_list.forEach((entry, i) => {
    const matches = Object.entries(selections).every(([axis, values]) =>
      values.includes(entryValue(entry, axis)),
    );
    if (matches) {
      chosen.push(i);
    }
  });
  return chosen;
}

// Benchmark-param selections as value indices per parameter position;
// default: every value.
function benchParamSelections(benchmark, state) {
  return (benchmark.params || []).map((values, position) => {
    const chosen = (state.benchParams[position] || []).filter(
      (idx) => idx >= 0 && idx < values.length,
    );
    return chosen.length ? chosen : values.map((_, idx) => idx);
  });
}

// Cartesian product of the selected indices, each with its flat index
// into the row-major product of all parameter axes (how parameterized
// graph values are stored) and its value labels.
function flatCombos(benchmark, perAxis) {
  const sizes = (benchmark.params || []).map((values) => values.length);
  let combos = [{ flat: 0, labels: [] }];
  perAxis.forEach((chosen, axisIdx) => {
    const stride = sizes.slice(axisIdx + 1).reduce((a, b) => a * b, 1);
    const next = [];
    for (const combo of combos) {
      for (const idx of chosen) {
        next.push({
          flat: combo.flat + idx * stride,
          labels: [...combo.labels, benchmark.params[axisIdx][idx]],
        });
      }
    }
    combos = next;
  });
  return combos;
}

// Axes whose value differs between the selected entries: only those
// are worth spelling out in series labels.
function varyingAxes(index, entryIndices) {
  const axes = [];
  for (const axis of Object.keys(index.params)) {
    const seen = new Set(
      entryIndices.map((i) => entryValue(index.graph_param_list[i], axis)),
    );
    if (seen.size > 1) {
      axes.push(axis);
    }
  }
  return axes;
}

function seriesLabel(index, entryIdx, varying, combo) {
  const parts = varying.map((axis) => {
    const value = entryValue(index.graph_param_list[entryIdx], axis);
    return `${axis}=${value === null ? NONE : value}`;
  });
  if (combo.labels.length) {
    parts.push(`(${combo.labels.join(", ")})`);
  }
  return parts.join(" ") || "value";
}

function unitsOf(benchmark) {
  return benchmark.units || benchmark.unit || "";
}

function tooltipPlugin(index, revs, units) {
  let tip = null;
  return {
    hooks: {
      init(u) {
        tip = el("div", "chart-tip");
        tip.hidden = true;
        u.over.append(tip);
        u.over.addEventListener("click", () => {
          if (u.select.width > 0) {
            return; // drag-select zoom, not a point click
          }
          const idx = u.cursor.idx;
          if (idx == null) {
            return;
          }
          const hash = index.revision_to_hash[revs[idx]];
          if (hash && index.show_commit_url) {
            window.open(index.show_commit_url + hash, "_blank", "noopener");
          }
        });
      },
      setCursor(u) {
        const idx = u.cursor.idx;
        if (idx == null || u.cursor.left < 0) {
          tip.hidden = true;
          return;
        }
        const hash = index.revision_to_hash[revs[idx]] || "";
        const date = index.revision_to_date[revs[idx]];
        const lines = [
          `<strong>${escapeHtml(hash.slice(0, index.hash_length))}</strong>` +
            (date ? ` ${new Date(date).toISOString().slice(0, 10)}` : ""),
        ];
        u.series.forEach((series, si) => {
          if (si === 0 || series.show === false) {
            return;
          }
          const value = u.data[si][idx];
          if (value != null) {
            lines.push(
              `${escapeHtml(series.label)}: ${value}` +
                (units ? ` ${escapeHtml(units)}` : ""),
            );
          }
        });
        tip.innerHTML = lines.join("<br>");
        tip.hidden = false;
        tip.style.left = `${u.cursor.left + 14}px`;
        tip.style.top = `${u.cursor.top + 14}px`;
      },
    },
  };
}

function toggleValue(list, value) {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

function selectorButton(label, active, onClick) {
  const button = el("button", active ? "sel active" : "sel", label);
  button.type = "button";
  button.addEventListener("click", onClick);
  return button;
}

function controlsPanel(index, benchmark, state, selections, perAxis) {
  const panel = el("section", "selectors");

  for (const [axis, values] of Object.entries(index.params)) {
    const group = el("fieldset", "axis-group");
    group.append(el("legend", "", axis));
    for (const value of values) {
      const label = value === null ? NONE : value;
      const active = selections[axis].includes(value);
      group.append(
        selectorButton(label, active, () => {
          const next = toggleValue(selections[axis], value);
          writeState({ ...state, axes: { ...selections, [axis]: next } });
        }),
      );
    }
    panel.append(group);
  }

  (benchmark.params || []).forEach((values, position) => {
    const group = el("fieldset", "axis-group");
    group.append(
      el("legend", "", benchmark.param_names[position] || `param ${position}`),
    );
    values.forEach((value, idx) => {
      const active = perAxis[position].includes(idx);
      group.append(
        selectorButton(value, active, () => {
          const nextParams = perAxis.map((chosen) => chosen.slice());
          nextParams[position] = toggleValue(perAxis[position], idx);
          const benchParams = {};
          nextParams.forEach((chosen, i) => {
            benchParams[i] = chosen;
          });
          writeState({ ...state, axes: selections, benchParams });
        }),
      );
    });
    panel.append(group);
  });

  const toggles = el("fieldset", "axis-group toggles");
  toggles.append(el("legend", "", "display"));
  toggles.append(
    selectorButton("log scale", state.log, () =>
      writeState({ ...state, axes: selections, log: !state.log }),
    ),
    selectorButton("date x-axis", state.x === "date", () =>
      writeState({ ...state, axes: selections, x: "date", zoom: null }),
    ),
    selectorButton("even x-axis", state.x === "even", () =>
      writeState({ ...state, axes: selections, x: "even", zoom: null }),
    ),
  );
  panel.append(toggles);
  return panel;
}

export async function renderGraphView(container, index, state) {
  if (currentChart) {
    currentChart.destroy();
    currentChart = null;
  }

  const benchmark = index.benchmarks[state.benchmark];
  if (!benchmark) {
    container.replaceChildren(
      el("p", "muted", `Unknown benchmark: ${state.benchmark}`),
    );
    return;
  }

  const selections = axisSelections(index, state);
  const perAxis = benchParamSelections(benchmark, state);
  const entryIndices = selectedEntryIndices(index, selections);
  const combos = flatCombos(benchmark, perAxis);
  const varying = varyingAxes(index, entryIndices);
  const units = unitsOf(benchmark);

  const title = el("h2", "bench-title", benchmark.pretty_name || benchmark.name);
  const controls = controlsPanel(index, benchmark, state, selections, perAxis);
  const chartWrap = el("div", "chart-wrap");
  container.replaceChildren(title, controls, chartWrap);

  const graphs = await Promise.all(
    entryIndices.map((i) => fetchGraph(graphUrl(index, i, state.benchmark))),
  );

  const revSet = new Set();
  graphs.forEach((graph) => {
    if (graph) {
      graph.forEach(([rev]) => revSet.add(rev));
    }
  });
  const revs = [...revSet].sort((a, b) => a - b);
  if (!revs.length) {
    chartWrap.append(el("p", "muted", "No data for this selection."));
    return;
  }
  const revPos = new Map(revs.map((rev, i) => [rev, i]));

  const xs =
    state.x === "date"
      ? revs.map((rev) => (index.revision_to_date[rev] ?? rev * 1000) / 1000)
      : revs.map((_, i) => i);

  const data = [xs];
  const seriesDefs = [{}];
  entryIndices.forEach((entryIdx, gi) => {
    const graph = graphs[gi];
    if (!graph) {
      return;
    }
    for (const combo of combos) {
      const column = new Array(revs.length).fill(null);
      graph.forEach(([rev, value]) => {
        const cell = Array.isArray(value) ? value[combo.flat] : value;
        column[revPos.get(rev)] = cell ?? null;
      });
      data.push(column);
      seriesDefs.push({
        label: seriesLabel(index, entryIdx, varying, combo),
        stroke: PALETTE[(seriesDefs.length - 1) % PALETTE.length],
        width: 1.5,
        points: { show: true, size: 5 },
      });
    }
  });

  if (data.length === 1) {
    chartWrap.append(el("p", "muted", "No data for this selection."));
    return;
  }

  const shortHash = (i) => {
    const hash = index.revision_to_hash[revs[i]] || "";
    return hash.slice(0, index.hash_length);
  };

  const opts = {
    width: Math.max(chartWrap.clientWidth || container.clientWidth, 280),
    height: 380,
    scales: {
      x: { time: state.x === "date" },
      y: state.log ? { distr: 3 } : {},
    },
    axes: [
      state.x === "even"
        ? {
            values: (u, splits) =>
              splits.map((s) =>
                Number.isInteger(s) && s >= 0 && s < revs.length
                  ? shortHash(s)
                  : "",
              ),
          }
        : {},
      { label: units || null },
    ],
    series: seriesDefs,
    plugins: [tooltipPlugin(index, revs, units)],
  };

  currentChart = new uPlot(opts, data, chartWrap);
  currentWrap = chartWrap;
  if (state.zoom) {
    currentChart.setScale("x", { min: state.zoom.min, max: state.zoom.max });
  }
}
