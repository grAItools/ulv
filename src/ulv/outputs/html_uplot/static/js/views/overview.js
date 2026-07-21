// Overview ranger: a thin mini plot of the same series as the main
// chart. Dragging on it selects the x range the main chart shows; the
// caller persists that range (in the URL hash) and re-renders, so the
// mini plot itself never zooms. Deliberately no tooltip plugin here —
// its click handler would open commit pages from the ranger.

export function renderOverview(container, { data, series, time, zoom, onZoom }) {
  const wrap = document.createElement("div");
  wrap.className = "overview-wrap";
  container.append(wrap);

  const showSelection = (u) => {
    if (!zoom) {
      return;
    }
    const left = u.valToPos(zoom.min, "x");
    const width = u.valToPos(zoom.max, "x") - left;
    if (Number.isFinite(left) && Number.isFinite(width) && width > 0) {
      // _fire=false: painting the current zoom window is not a user
      // drag and must not loop back into onZoom
      u.setSelect(
        { left, width, top: 0, height: u.over.clientHeight },
        false,
      );
    }
  };

  const opts = {
    width: Math.max(wrap.clientWidth || container.clientWidth, 280),
    height: 60,
    scales: { x: { time } },
    axes: [{ show: false }, { show: false }],
    legend: { show: false },
    cursor: {
      y: false,
      points: { show: false },
      // select a range only; zooming the mini plot itself would
      // destroy the overview
      drag: { x: true, y: false, setScale: false },
    },
    series: [
      {},
      ...series.map((s) => ({
        stroke: s.stroke,
        width: 1,
        points: { show: false },
        // mirror the main chart's legend-hidden state so a series the
        // user hid there is not still drawn in the ranger
        show: s.show !== false,
      })),
    ],
    plugins: [
      {
        hooks: {
          setSelect(u) {
            if (u.select.width > 0) {
              const min = u.posToVal(u.select.left, "x");
              const max = u.posToVal(u.select.left + u.select.width, "x");
              onZoom(min, max);
            }
          },
          ready(u) {
            showSelection(u);
          },
        },
      },
    ],
  };

  const chart = new uPlot(opts, data, wrap);
  // setSize() clears the painted zoom window; expose a repaint so the
  // resize handler can restore it after re-fitting the overview.
  chart.repaintSelection = () => showSelection(chart);
  return chart;
}
