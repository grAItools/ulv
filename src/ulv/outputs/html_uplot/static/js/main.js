// App entry point: boot from info.json + index.json (relative fetches,
// so the site works from any subdirectory), render the shell, and
// re-render the active view on every hash change — the hash is the
// only source of view state (see state.js).

import { renderNav } from "./nav.js";
import { readState, writeState } from "./state.js";
import { renderGraphView } from "./views/graph.js";

let siteIndex = null;

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`);
  }
  return response.json();
}

function showMessage(text) {
  const main = document.querySelector("#main-pane");
  const message = document.createElement("p");
  message.className = "muted";
  message.textContent = text;
  main.replaceChildren(message);
}

async function render() {
  const state = readState();
  if (!state.benchmark) {
    const total = Object.keys(siteIndex.benchmarks).length;
    showMessage(`${total} benchmarks — select one to view its history`);
    return;
  }
  await renderGraphView(document.querySelector("#main-pane"), siteIndex, state);
}

async function boot() {
  const [info, index] = await Promise.all([
    fetchJson("info.json"),
    fetchJson("index.json"),
  ]);
  siteIndex = index;

  const project = index.project || "benchmarks";
  document.title = project;
  const link = document.querySelector("#project-link");
  link.textContent = project;
  if (index.project_url && index.project_url !== "#") {
    link.href = index.project_url;
  }
  if (info.timestamp) {
    document.querySelector("#generated-at").textContent =
      `generated ${new Date(info.timestamp).toISOString().slice(0, 10)}`;
  }

  const names = Object.keys(index.benchmarks).sort();
  renderNav(document.querySelector("#bench-nav"), names, (name) => {
    // switching benchmark keeps axis/display choices but drops the
    // benchmark-param selections, which are per-benchmark
    writeState({ ...readState(), benchmark: name, benchParams: {} });
  });

  window.addEventListener("hashchange", () => {
    render().catch((error) => showMessage(`Render failed: ${error.message}`));
  });
  await render();
}

boot().catch((error) => {
  showMessage(`Failed to load site data: ${error.message}`);
  throw error;
});
