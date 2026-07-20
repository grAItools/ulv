// View state lives in the URL fragment as URLSearchParams, so copying
// the URL restores the same view in a fresh session. State flows one
// way: every UI mutation writes the hash, and rendering always starts
// from readState() — nothing renders from in-memory state alone.
//
// Keys: view, benchmark, log, x, zoom; parameter-axis selections as
// repeated "p-<axis>" keys; benchmark-param selections as repeated
// "b-<position>" keys holding value indices; legend-hidden series as
// repeated "hide" keys holding permutation indices.

const AXIS_PREFIX = "p-";
const BENCH_PARAM_PREFIX = "b-";

// Spelling for a null axis value, matching how the site data sorts it.
export const NONE = "[none]";

export function readState() {
  const params = new URLSearchParams(location.hash.slice(1));
  const state = {
    view: params.get("view") || "graph",
    benchmark: params.get("benchmark"),
    log: params.get("log") === "1",
    x: params.get("x") === "even" ? "even" : "date",
    zoom: null,
    hidden: params.getAll("hide").map(Number).filter(Number.isInteger),
    axes: {},
    benchParams: {},
  };
  const zoom = params.get("zoom");
  if (zoom) {
    const [min, max] = zoom.split(",").map(Number);
    if (Number.isFinite(min) && Number.isFinite(max)) {
      state.zoom = { min, max };
    }
  }
  for (const key of new Set(params.keys())) {
    if (key.startsWith(AXIS_PREFIX)) {
      state.axes[key.slice(AXIS_PREFIX.length)] = params
        .getAll(key)
        .map((value) => (value === NONE ? null : value));
    } else if (key.startsWith(BENCH_PARAM_PREFIX)) {
      const raw = key.slice(BENCH_PARAM_PREFIX.length);
      const position = Number(raw);
      // Number("") === 0, so a bare "b-" key would masquerade as
      // position 0 and clobber a real selection; require actual digits.
      if (raw !== "" && Number.isInteger(position) && position >= 0) {
        state.benchParams[position] = params
          .getAll(key)
          .map(Number)
          .filter(Number.isInteger);
      }
    }
  }
  return state;
}

export function encodeState(state) {
  const params = new URLSearchParams();
  if (state.view && state.view !== "graph") {
    params.set("view", state.view);
  }
  if (state.benchmark) {
    params.set("benchmark", state.benchmark);
  }
  for (const [axis, values] of Object.entries(state.axes || {})) {
    for (const value of values) {
      params.append(AXIS_PREFIX + axis, value === null ? NONE : value);
    }
  }
  for (const [position, indices] of Object.entries(state.benchParams || {})) {
    for (const index of indices) {
      params.append(BENCH_PARAM_PREFIX + position, String(index));
    }
  }
  for (const index of state.hidden || []) {
    params.append("hide", String(index));
  }
  if (state.log) {
    params.set("log", "1");
  }
  if (state.x === "even") {
    params.set("x", "even");
  }
  if (state.zoom) {
    params.set("zoom", `${state.zoom.min},${state.zoom.max}`);
  }
  return params.toString();
}

export function writeState(state) {
  location.hash = "#" + encodeState(state);
}
