// Grid view: one card per benchmark with a thumbnail of its
// cross-environment summary graph. Thumbnails render lazily via
// IntersectionObserver — only cards scrolled into view fetch their
// summary file (from the manifest's summary_dir + stem, see data.js).

import { fetchGraph, summaryUrl } from "../data.js";
import { writeState } from "../state.js";

let observer = null;

function drawThumbnail(card, index, name) {
  fetchGraph(summaryUrl(index, name)).then((graph) => {
    const slot = card.querySelector(".thumb");
    const points = (graph || []).filter(([, value]) => value != null);
    if (!points.length) {
      slot.textContent = "no data";
      slot.classList.add("muted");
      return;
    }
    const data = [graph.map(([rev]) => rev), graph.map(([, value]) => value)];
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
    );
  });
}

export function renderGridView(container, index, state) {
  if (observer) {
    observer.disconnect();
  }
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

  const grid = document.createElement("div");
  grid.className = "grid";
  for (const name of Object.keys(index.benchmarks).sort()) {
    const benchmark = index.benchmarks[name];
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.name = name;

    const title = document.createElement("h3");
    title.textContent = benchmark.pretty_name || name;
    const thumb = document.createElement("div");
    thumb.className = "thumb";
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
