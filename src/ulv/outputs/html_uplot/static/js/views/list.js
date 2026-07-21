// List view: the summary rows of the current parameter selection as a
// sortable table of benchmark / last value (+ units) / error. The
// step-detection columns (prev_value / change_rev in the rows data)
// are dropped — ulv always emits null for them (spec Decision 5).

import { el } from "../dom.js";
import { fetchGraph, summaryRowsUrl } from "../data.js";
import { writeState } from "../state.js";
import { axisSelections, selectedEntryIndices, unitsOf } from "./graph.js";

// Monotonic render id, mirroring graph.js: a hashchange during the
// in-flight summary fetch starts a second render, and only the newest
// may paint (see renderListView).
let renderToken = 0;

const COLUMNS = [
  ["pretty_name", "Benchmark"],
  ["last_value", "Last value"],
  ["last_err", "Error"],
];

function compareBy(key, direction) {
  return (a, b) => {
    const [x, y] = [a[key], b[key]];
    if (x == null) {
      return y == null ? 0 : 1; // nulls sort last either direction
    }
    if (y == null) {
      return -1;
    }
    const order =
      typeof x === "number" && typeof y === "number"
        ? x - y
        : String(x).localeCompare(String(y));
    return order * direction;
  };
}

function formatValue(value, units) {
  if (value == null) {
    return "";
  }
  const text = typeof value === "number" ? String(+value.toPrecision(6)) : value;
  return units ? `${text} ${units}` : `${text}`;
}

export async function renderListView(container, index, state) {
  const token = ++renderToken;
  const selections = axisSelections(index, state);
  const entryIndices = selectedEntryIndices(index, selections);
  if (!entryIndices.length) {
    container.replaceChildren(
      el("p", "muted", "No environment matches the current selection."),
    );
    return;
  }

  // one rows file per environment directory; like the vendored list
  // view, show the first matching combination
  const rows = await fetchGraph(summaryRowsUrl(index, entryIndices[0]));
  // A newer render (e.g. rapid back/forward) superseded this one while
  // its fetch was in flight; bail so the stale rows never paint over it.
  if (token !== renderToken) {
    return;
  }
  if (!rows || !rows.length) {
    container.replaceChildren(el("p", "muted", "No data for this selection."));
    return;
  }

  const table = el("table", "data-table list-table");
  const head = el("tr");
  let sortKey = "pretty_name";
  let direction = 1;

  const body = el("tbody");
  const renderRows = () => {
    rows.sort(compareBy(sortKey, direction));
    body.replaceChildren(
      ...rows.map((row) => {
        const units = unitsOf(index.benchmarks[row.name] || {});
        const tr = el("tr");
        for (const [key] of COLUMNS) {
          tr.append(
            el(
              "td",
              "",
              key === "pretty_name"
                ? row.pretty_name
                : formatValue(row[key], units),
            ),
          );
        }
        tr.addEventListener("click", () => {
          writeState({
            ...state,
            view: "graph",
            benchmark: row.name,
            benchParams: {},
            hidden: [],
          });
        });
        return tr;
      }),
    );
  };

  for (const [key, label] of COLUMNS) {
    const th = el("th", "", label);
    th.addEventListener("click", () => {
      direction = key === sortKey ? -direction : 1;
      sortKey = key;
      renderRows();
    });
    head.append(th);
  }

  const thead = el("thead");
  thead.append(head);
  table.append(thead, body);
  renderRows();
  container.replaceChildren(table);
}
