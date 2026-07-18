// App entry point: boot from info.json + index.json (relative fetches,
// so the site works from any subdirectory) and render the shell.
// Graph, grid and list views mount into #main-pane.

import { renderNav } from "./nav.js";

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`);
  }
  return response.json();
}

function setStatus(text) {
  const status = document.querySelector("#status");
  if (status) {
    status.textContent = text;
  }
}

async function boot() {
  const [info, index] = await Promise.all([
    fetchJson("info.json"),
    fetchJson("index.json"),
  ]);

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
    location.hash = `#benchmark=${encodeURIComponent(name)}`;
  });
  setStatus(`${names.length} benchmarks — select one to view`);
}

boot().catch((error) => {
  setStatus(`Failed to load site data: ${error.message}`);
  throw error;
});
