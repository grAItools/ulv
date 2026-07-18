# Tasks

Mirror of `plan.md`. Tick as you go; every phase ends with
`make verify` green.

## Phase 1 — Additive `graph_paths` manifest in `index.json`

- [x] Emit `graph_paths` (`dirs` ∥ `graph_param_list`, `summary_dir`,
      `benchmarks` name → sanitized stem) from `_index_data`, derived
      via `paths.graph_path` / `sanitize_filename`
- [x] Tests: `dirs` parallel + equal to `graph_path(entry, "x")`
      dirnames; dirs exist on disk; stems = `sanitize_filename(name)`;
      summary files exist per stem
- [x] Test: machine-less BMF site with `::` names — every emitted
      graph file reachable through the manifest
- [x] Vendored generator suites pass unmodified (additivity)
- [x] `make verify` green

## Phase 2 — `html-uplot` generator skeleton

- [ ] Author ADR 0008: uPlot frontend supersedes ADR 0003's "reuse
      ASV UI"; vendoring policy carried forward; ECharts fallback
- [ ] Extract `src/ulv/outputs/common.py` (atomic swap, graph build,
      summarylist, index data, snapshot rows); `HtmlOutputGenerator`
      delegates; existing tests pass unchanged
- [ ] Vendor uPlot 1.6.x (`uPlot.iife.min.js`, `uPlot.min.css`) with
      sha256 verified from two sources; write `html_uplot/VENDORED.md`
      and `LICENSES/uplot.txt`
- [ ] `HtmlUplotOutputGenerator` (`name = "html-uplot"`) in
      `src/ulv/outputs/html_uplot/generator.py`: static copy, shared
      data emission, own snapshot page; register as built-in
- [ ] Static skeleton: `index.html` (viewport meta), `app.css`
      (responsive shell), `js/main.js` fetching `info.json`/`index.json`
      and rendering the nav tree
- [ ] CLI/config: `--generator` flag + `output_generator` key
      (default `html`); unknown generator → `UlvError` listing names
- [ ] Tests: payload budget < 100,000 bytes; uPlot sha256 pinned; no
      absolute URLs anywhere in the new static tree (JS included);
      static-suffix check; snapshot page (values, bounds
      empty-not-zero, local CSS); atomic-swap tests on new generator;
      default build still vendored frontend
- [ ] E2e: crawl `html-uplot` ASV + BMF sites from a subdirectory,
      following module scripts and static imports; manifest dirs and
      all graph files return 200
- [ ] Wheel test: static tree, vendor files, `VENDORED.md`,
      `LICENSES/uplot.txt` ship; site builds from installed wheel
- [ ] Config/CLI precedence tests for `--generator`
- [ ] Manual smoke: served site shows nav tree
- [ ] `make verify` green

## Phase 3 — Graph view core

- [ ] `js/data.js`: manifest-only graph fetches (encodeURIComponent
      per segment); missing file → "no data", not an error
- [ ] `js/state.js`: hash codec (view, benchmark, params, log, x-axis,
      zoom); every UI mutation writes the hash
- [ ] `js/views/graph.js`: generic selector panels from
      `index.params` (`null` as `[none]`); benchmark-param
      sub-selection; uPlot series per permutation; units in y-axis
      label; log toggle; date/even-spacing toggle; tooltip with value
      + units + short hash; point click → commit URL
- [ ] Static test: app-shell JS contains no `machine` token
- [ ] Crawl covers new modules; budget still green
- [ ] Manual: graphs render and behave on ASV and BMF fixture sites
- [ ] `make verify` green

## Phase 4 — Overview ranger, series toggling, touch plugin

- [ ] `js/views/overview.js`: mini plot, drag-select zoom, zoom in hash
- [ ] Legend with per-series show/hide, state in hash
- [ ] `js/touch.js`: pinch-zoom/pan plugin (uPlot hooks); provenance
      line in `html_uplot/VENDORED.md`
- [ ] Static tests: modules crawled, budget green, `touch.js`
      referenced, no absolute URLs
- [ ] Manual: drag-zoom, legend toggling, pinch/pan via touch emulation
- [ ] `make verify` green

## Phase 5 — Grid and list views

- [ ] `js/views/grid.js`: lazy thumbnails (IntersectionObserver) from
      `summary_dir` + stem; card click → graph view
- [ ] `js/views/list.js`: summary rows via manifest; name/value
      (+ units)/error columns; self-authored sort; no dead columns
- [ ] Static test: no "Recent change" / "Changed at" in shipped app
      code; crawl + budget green
- [ ] E2e: every manifest-derived thumbnail URL returns 200 on the
      BMF (`::`-named) site
- [ ] Manual: thumbnails lazy-load, sorting works, units visible
- [ ] `make verify` green

## Phase 6 — Docs, vendoring polish, parity checklist

- [ ] `docs/architecture.md`: module map (+`common`, +`html_uplot`),
      `graph_paths` contract, units gap closed, ADR 0008 linked
- [ ] User docs: `--generator html-uplot` / `output_generator` example;
      vendored generator remains default
- [ ] `CHANGELOG.md`: bullets for new generator + manifest
- [ ] Final `html_uplot/VENDORED.md` + `LICENSES/` review
- [ ] `make verify` green

### Manual parity checklist (run on ASV fixture site AND a machine-less BMF site, both served from a subdirectory)

- [ ] Nav tree; param selectors; benchmark-param sub-selection
- [ ] Log toggle; date vs. even-spacing toggle
- [ ] Hover tooltip; units shown on the Bencher-units fixture
- [ ] Commit click-through honors URL template + hash length
- [ ] Overview drag-zoom; legend series toggling
- [ ] Pinch-zoom/pan (devtools touch emulation or device)
- [ ] Grid lazy thumbnails; list sorting; no dead columns
- [ ] Hash round-trip for representative states (fresh tab restores)
- [ ] Phone-width viewport: no horizontal chrome scrolling
- [ ] Machine-less site: no machine selector; machine site: machine is
      an ordinary axis
- [ ] Devtools network tab: only the site's own static files fetched
