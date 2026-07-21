// Graph data access, strictly through the graph_paths manifest in
// index.json: any graph file is dirs[i] + "/" + stem + ".json", so the
// frontend never recomputes sanitized paths from raw benchmark names.

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

// URL of the graph file for one graph_param_list entry (by position)
// and one benchmark.
export function graphUrl(index, dirIndex, benchmarkName) {
  const manifest = index.graph_paths;
  const stem = manifest.benchmarks[benchmarkName];
  return encodePath(`${manifest.dirs[dirIndex]}/${stem}.json`);
}

// URL of a benchmark's cross-environment summary graph (grid thumbnails).
export function summaryUrl(index, benchmarkName) {
  const manifest = index.graph_paths;
  const stem = manifest.benchmarks[benchmarkName];
  return encodePath(`${manifest.summary_dir}/${stem}.json`);
}

// URL of one environment directory's summary-rows file (list view).
export function summaryRowsUrl(index, dirIndex) {
  return encodePath(`${index.graph_paths.dirs[dirIndex]}/summary.json`);
}

// A missing graph file means "no data for this combination", never an
// error: not every param combination × benchmark has results.
export async function fetchGraph(url) {
  const response = await fetch(url);
  if (!response.ok) {
    return null;
  }
  return response.json();
}
