# Changelog

All notable changes to this project are documented here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `ulv build --generator html-uplot` (config key `output_generator`) selects
  a new self-authored uPlot frontend: under 100 KB of shipped assets,
  mobile-responsive, machine-less datasets first-class, and Bencher measure
  units shown with plotted values. The vendored ASV frontend remains the
  default. See ADR 0008.
- `index.json` gains an additive `graph_paths` manifest (graph directories
  parallel to `graph_param_list`, summary directory, benchmark name → file
  stem) so frontends can locate every graph file without recomputing
  sanitized paths client-side; existing consumers are unaffected.
- Continuous integration on GitHub Actions: every pull request and push to
  `main` is gated by lint, format-check, tests (Python 3.12–3.14), and the
  docs build; PR titles are validated against Conventional Commits; tagging
  `vX.Y.Z` builds artifacts, smoke-tests the wheel, and cuts a GitHub Release
  (PyPI publishing scaffolded but disabled). See ADR 0007.

### Changed

- Minimum supported Python is now 3.12 (dropped 3.11), matching the CI matrix.
- `make verify` now also runs `ruff format --check`, so formatting is enforced
  by the local gate as well as CI.

## [0.1.0] — 2026-07-17

### Added

- `ulv build` generates a self-contained static benchmark dashboard
  (vendored ASV frontend, no network requests, works under a non-root
  URL path) with atomic output — a failed build never leaves a broken
  site.
- `asv` input: reads native ASV results directories (api_version 2)
  losslessly — machines, environment/param axes, parameterized
  benchmarks, stats — ordering revisions by result date.
- Optional git enrichment for the `asv` input (`--repo`, `--branches`):
  topological commit ordering, committer dates, tags, and per-branch
  attribution; unattributable results are warned about and skipped.
- `bmf` input: reads Bencher Metric Format files with explicit sidecar
  metadata (`--manifest`, `--filename-pattern`, or per-file flags);
  ordering never comes from file order or timestamps. A lone snapshot
  renders as a static `snapshot.html` table with value bounds.
- `bencher-api` input: read-only paginated fetch of a project's
  reports from a Bencher server (`--bencher-url`, `--bencher-project`;
  token via `BENCHER_API_TOKEN`, `bencher_token`, or `--bencher-token`,
  never echoed in errors), e.g.
  `ulv build -i bencher-api --bencher-project myproj -o site/`.
- Testbed decomposition (`[testbeds]` config table or
  `--testbeds-file`): maps Bencher testbeds onto independent factor
  axes; uncovered testbeds fail the build naming every one, or are
  included with "unknown" values under `--allow-unmapped`.
- Config file support (`ulv.toml`/`.json`, `--config`) with
  defaults < file < flags precedence; every scalar setting has a flag.
- `ulv serve` previews a built site locally (`ulv serve site/ --port
  8080`; directory defaults to the config's `output_dir`).
- Plugin architecture: third-party input formats and output generators
  register via `ulv.input_formats`/`ulv.output_generators` entry
  points or `register()` calls, without modifying shipped code.
- User documentation under `docs/user/`: quickstart, a guide per input
  format, config and testbed guides, and a CLI reference generated from
  the parser (`make docs`; `make verify` fails if it drifts).

[Unreleased]: https://github.com/grAItools/ulv/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/grAItools/ulv/releases/tag/v0.1.0
