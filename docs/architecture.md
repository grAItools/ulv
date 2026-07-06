# Architecture

## High-level

Unladen Velocity (`ulv`) turns existing benchmark result data — native
ASV results, Bencher Metric Format files, or results fetched from a
Bencher server — into a self-contained static HTML site servable by any
plain file server:

```
input plugin ──> Dataset (ulv.model) ──> output generator ──> static site
   (asv, bmf,                              (html: vendored
    bencher-api)                            ASV frontend)
```

Typical invocations:

```
ulv build -i asv --input-dir results/ -o site/ --project myproj
ulv build -i asv --input-dir results/ -o site/ --repo . --branches main,dev
ulv build -i bmf --input-dir bmf/ --manifest bmf/manifest.json -o site/
ulv build -i bmf --input-dir bmf/ --filename-pattern "{commit}_{date}.json" -o site/
ulv build -i bencher-api --bencher-project myproj -o site/
ulv build --config ulv.toml
ulv serve site/ --port 8080
```

## Module map

| Module | Owns |
| --- | --- |
| `ulv.model` | Frozen `Dataset` (`Revision`, `Environment`, `Benchmark`, `ResultSeries`, `ResultPoint`); referential-integrity validation; `has_time_axis` (a single-revision dataset renders as a snapshot table, not graphs) |
| `ulv.plugins` | `InputFormat`/`OutputGenerator` protocols, per-kind registries, entry-point discovery ([ADR 0002](adr/0002-plugin-discovery-via-entry-points.md)) |
| `ulv.errors` | `UlvError(message, offending_input=…)`, the single user-facing error type; the CLI maps it (and `OSError`) to a one-line diagnostic + exit 1 |
| `ulv.config` | `Settings` dataclass, TOML/JSON config loading, precedence defaults < file < flags ([ADR 0004](adr/0004-argparse-cli-with-config-file-precedence.md)) |
| `ulv.testbeds` | User-supplied testbed → factor decomposition (spec Decisions 8-9); shared by every input with a testbed notion |
| `ulv.gitrepo` | Read-only `git` CLI wrapper for optional enrichment (topological order, committer dates, tags, first-parent branch membership) |
| `ulv.cli` | argparse CLI: `build`, `serve` |
| `ulv.inputs.asv` | Native ASV results directories (api_version 2), lossless mapping, optional git enrichment |
| `ulv.inputs.bmf` | Bencher Metric Format files with explicit sidecar metadata (manifest / filename pattern / flags) |
| `ulv.inputs.bencher_api` | Read-only paginated fetch from a Bencher server ([ADR 0005](adr/0005-stdlib-http-client-with-transport-seam.md)) |
| `ulv.outputs.html.generator` | Site assembly: graphs, summaries, summarylist, `index.json`/`info.json`, snapshot page, atomic output swap |
| `ulv.outputs.html.graphs` | Port of asv's graph data handling (averaging, NA trim, summary geometric means, resampling) minus step detection |
| `ulv.outputs.html.paths` | Graph file paths, byte-compatible with the frontend's `graph_to_path` |
| `ulv.outputs.html.static/` | Vendored ASV frontend + pinned third-party libraries ([ADR 0003](adr/0003-vendor-asv-frontend-and-third-party-js.md)); patches and hashes in [`VENDORED.md`](../src/ulv/outputs/html/VENDORED.md), attributions in `LICENSES/` |

## Plugin architecture

Two registries in `ulv.plugins` (`input_formats`, `output_generators`)
hold the built-ins, registered at import time. Adding a format or
generator without touching shipped code:

- **Installed package:** expose an entry point in group
  `ulv.input_formats` or `ulv.output_generators` pointing at a class
  (instantiated with no arguments) or a ready instance.
- **In-process:** call `input_formats.register(plugin)` /
  `output_generators.register(plugin)`.

An input format provides `name` and `load(source, options) -> Dataset`;
an output generator `name` and `generate(dataset, out_dir, options)`.
Explicit registrations always win over entry points, so a third-party
package can never shadow a built-in ([ADR 0002](adr/0002-plugin-discovery-via-entry-points.md)).

## Semantics worth knowing

- **Revision numbering is dense.** Revisions are numbered by their
  index in the dataset (0..n-1), unlike asv, which numbers by position
  in the full `rev-list --all` history. Consequence: tags pointing at
  commits with no benchmark results are dropped rather than given a
  revision number.
- **Commit dates use the committer date (`%ct`).** asv reads the
  author date (`%at`); the two differ only for rebased or
  cherry-picked commits.
- **Branch attribution is per containing branch.** With a repository
  configured, a result is graphed once on every configured branch
  containing its commit (asv's semantics); results on no configured
  branch, or whose commit history no longer contains, are warned about
  and skipped, never mis-attributed.
- **BMF ordering is metadata-only** (spec Decision 3): a manifest,
  a filename pattern, or per-file flags — never file order, name
  order, or mtimes. A lone snapshot needs no metadata and renders as a
  table (`snapshot.html`, with `index.html` a redirect to it).
- **Output is atomic.** Sites build in a hidden sibling directory and
  swap in on success; a failed build leaves either no output or the
  previous site intact.

## External dependencies

None at runtime. The stdlib covers TOML/JSON config (`tomllib`,
`json`), HTTP fetch (`urllib.request`, [ADR 0005](adr/0005-stdlib-http-client-with-transport-seam.md)),
the CLI (`argparse`, [ADR 0004](adr/0004-argparse-cli-with-config-file-precedence.md)),
and the preview server (`http.server`). Git enrichment shells out to
the `git` CLI. The vendored frontend third-party JS/CSS is pinned and
attributed per [ADR 0003](adr/0003-vendor-asv-frontend-and-third-party-js.md).

## Boundaries

- **CLI**: `ulv build` (read inputs, write a site), `ulv serve`
  (local preview only — the published site needs no server logic).
- **Outbound HTTP**: only the `bencher-api` input, read-only GETs.
- **Generated sites** perform no network requests beyond fetching
  their own static files.

## Deferred / future work

- **Git enrichment for BMF/Bencher inputs** (plan Phase 8 step 2
  anticipated it): the `bmf` and `bencher-api` inputs reject the
  `repo`/`branches` settings with explicit errors instead of wiring
  `ulv.gitrepo` in. Their ordering is metadata-/timestamp-driven by
  design (spec Decision 3); enriching commit order and links from a
  repository is compatible with the model (`Revision` already carries
  the fields) and can be added behind the existing settings without
  breaking anything.
- **Regression detection** is out of scope for v1 (spec Decision 6):
  summarylist change columns stay null; asv's `step_detect` was
  deliberately not ported.
- **Bencher measure units**: the human-readable units string rides in
  `Benchmark.extra["units"]`; the frontend currently displays the
  measure slug.

## Generated code

Anything under `*/generated/` is regenerated by your project's codegen
pipeline (define it as a target in your task runner or as a standalone
script). Agents must not edit generated files. (`src/ulv/outputs/html/static/`
is vendored, not generated — see `VENDORED.md` — and is excluded from
lint/format instead.)

## See also

- ADRs of record: [`adr/`](adr/) — notably
  [0002 plugin discovery](adr/0002-plugin-discovery-via-entry-points.md),
  [0003 vendored frontend](adr/0003-vendor-asv-frontend-and-third-party-js.md),
  [0004 argparse + config precedence](adr/0004-argparse-cli-with-config-file-precedence.md),
  [0005 stdlib HTTP transport](adr/0005-stdlib-http-client-with-transport-seam.md)
- Style guide: [`style.md`](style.md)
- Testing strategy: [`testing.md`](testing.md)
