// List view: the summary rows of the current parameter selection as a
// sortable table of benchmark / last value (+ units) / error. The
// step-detection columns (prev_value / change_rev in the rows data)
// are dropped — ulv always emits null for them (spec Decision 5).

import { fetchGraph, summaryRowsUrl } from "../data.js";
import { writeState } from "../state.js";
import { axisSelections, selectedEntryIndices } from "./graph.js";

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
  const selections = axisSelections(index, state);
  const entryIndices = selectedEntryIndices(index, selections);
  const message = document.createElement("p");
  message.className = "muted";
  if (!entryIndices.length) {
    message.textContent = "No environment matches the current selection.";
    container.replaceChildren(message);
    return;
  }

  // one rows file per environment directory; like the vendored list
  // view, show the first matching combination
  const rows = await fetchGraph(summaryRowsUrl(index, entryIndices[0]));
  if (!rows || !rows.length) {
    message.textContent = "No data for this selection.";
    container.replaceChildren(message);
    return;
  }

  const table = document.createElement("table");
  table.className = "data-table list-table";
  const head = document.createElement("tr");
  let sortKey = "pretty_name";
  let direction = 1;

  const body = document.createElement("tbody");
  const renderRows = () => {
    rows.sort(compareBy(sortKey, direction));
    body.replaceChildren(
      ...rows.map((row) => {
        const units =
          (index.benchmarks[row.name] || {}).units ||
          (index.benchmarks[row.name] || {}).unit ||
          "";
        const tr = document.createElement("tr");
        for (const [key] of COLUMNS) {
          const td = document.createElement("td");
          td.textContent =
            key === "pretty_name"
              ? row.pretty_name
              : formatValue(row[key], units);
          tr.append(td);
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
    const th = document.createElement("th");
    th.textContent = label;
    th.addEventListener("click", () => {
      direction = key === sortKey ? -direction : 1;
      sortKey = key;
      renderRows();
    });
    head.append(th);
  }

  const thead = document.createElement("thead");
  thead.append(head);
  table.append(thead, body);
  renderRows();
  container.replaceChildren(table);
}
