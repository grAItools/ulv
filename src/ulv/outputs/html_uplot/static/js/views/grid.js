// Grid view: one card per benchmark with a thumbnail of its
// cross-environment summary graph. Thumbnails render lazily via
// IntersectionObserver — only cards scrolled into view fetch their
// summary file (from the manifest's summary_dir + stem, see data.js).

import { el } from "../dom.js";
import { fetchGraph, summaryUrl } from "../data.js";
import { writeState } from "../state.js";

let observer = null;
// Every uPlot instance registers a window "dppxchange" listener that
// only destroy() removes, so an un-destroyed thumbnail is retained
// forever — canvas, data and DOM subtree — and re-renders on browser
// zoom/monitor changes. Track each batch and destroy it before the
// next render or on view switch.
let thumbCharts = [];

export function destroyThumbnails() {
  if (observer) {
    observer.disconnect();
    observer = null;
  }
  for (const chart of thumbCharts) {
    chart.destroy();
  }
  thumbCharts = [];
}

function drawThumbnail(card, index, name) {
  fetchGraph(summaryUrl(index, name)).then((graph) => {
    const slot = card.querySelector(".thumb");
    if (!slot.isConnected) {
      return; // view switched while the summary fetch was in flight
    }
    const points = (graph || []).filter(([, value]) => value != null);
    if (!points.length) {
      slot.textContent = "no data";
      slot.classList.add("muted");
      return;
    }
    const data = [graph.map(([rev]) => rev), graph.map(([, value]) => value)];
    thumbCharts.push(
      new uPlot(
        {
          width: slot.clientWidth || 220,
          height: 60,
          axes: [{ show: false }, { show: false }],
          legend: { show: false },
          cursor: { show: false },
          scales: { x: { time: false } },
          series: [{}, { stroke: "#1a5fb4", width: 1, points: { show: false } }],
        },
        data,
        slot,
      ),
    );
  });
}

export function renderGridView(container, index, state) {
  destroyThumbnails();
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          observer.unobserve(entry.target);
          drawThumbnail(entry.target, index, entry.target.dataset.name);
        }
      }
    },
    { rootMargin: "200px" },
  );

  const grid = el("div", "grid");
  for (const name of Object.keys(index.benchmarks).sort()) {
    const benchmark = index.benchmarks[name];
    const card = el("article", "card");
    card.dataset.name = name;

    const title = el("h3", "", benchmark.pretty_name || name);
    const thumb = el("div", "thumb");
    card.append(title, thumb);

    card.addEventListener("click", () => {
      // hidden/benchParams are positional per benchmark; start clean
      writeState({
        ...state,
        view: "graph",
        benchmark: name,
        benchParams: {},
        hidden: [],
      });
    });

    grid.append(card);
    observer.observe(card);
  }
  container.replaceChildren(grid);
}
