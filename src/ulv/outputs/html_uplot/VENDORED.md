# Vendored assets — `html-uplot` frontend

Policy (ADR 0008, carrying ADR 0003's forward): pinned plain files,
recorded sources and integrity hashes, license attribution under
`LICENSES/`, and **no local patches** — behavior gaps are closed in the
self-authored app-shell code instead. Update by re-vendoring a newer
pinned release and re-verifying hashes from two independent sources.

Everything under `static/` outside `static/vendor/` is authored by this
project (BSD-3-Clause, like the rest of ulv) and is not vendored.
One provenance note: `static/js/touch.js` (pinch-zoom/pan via uPlot's
plugin hooks) is self-authored but derived from the `zoom-touch` demo
shipped in the pinned uPlot release (`demos/zoom-touch.html`, MIT, same
upstream and license as above).

## uPlot 1.6.32

- Upstream: <https://github.com/leeoniya/uPlot> — MIT, see
  `LICENSES/uplot.txt`.
- Files: `static/vendor/uPlot.iife.min.js`, `static/vendor/uPlot.min.css`,
  taken unmodified from the published `dist/` artifacts.
- Provenance: fetched 2026-07-18 from two independent sources, which
  agreed byte-for-byte (npm tarballs carry no SRI annotation, so the
  cross-source check substitutes for one):
  - npm registry tarball: `https://registry.npmjs.org/uplot/-/uplot-1.6.32.tgz`
    (paths `package/dist/uPlot.iife.min.js`, `package/dist/uPlot.min.css`)
  - jsDelivr: `https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.iife.min.js`,
    `https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css`
- sha256 (pinned in `tests/test_output_html_uplot.py`):
  - `uPlot.iife.min.js`:
    `19c8d4c6ad88929a79f4ae49d6f7161566dfd0ba3d15cc495e974f787eb78f1f`
  - `uPlot.min.css`:
    `df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04`
- Fallback if uPlot becomes untenable: ECharts, re-vendored under this
  same policy (ADR 0008).
