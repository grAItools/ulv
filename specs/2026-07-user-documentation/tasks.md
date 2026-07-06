# Tasks

## Phase 1 — Directory scaffold and quickstart

- [x] Create `docs/user/index.md` with intro and table of contents
- [x] Create `docs/user/quickstart.md` with prerequisites, clone, install, build, serve steps
- [x] Manually verify quickstart commands run successfully

## Phase 2 — ASV format guide

- [x] Create `docs/user/asv.md` covering directory layout
- [x] Document minimal `ulv build -i asv` invocation
- [x] Document `--project` option
- [x] Document git enrichment: `--repo`, `--branches`, `--show-commit-url`
- [x] Verify example commands run against `tests/fixtures/asv_results/`

## Phase 3 — BMF format guide with dedicated sample

- [x] Create `docs/user/samples/bmf/` directory
- [x] Add 2-3 sample BMF `.json` files
- [x] Add `docs/user/samples/bmf/manifest.json`
- [x] Create `docs/user/bmf.md` covering BMF structure
- [x] Document single-file invocation with `--commit`, `--date`, `--testbed`
- [x] Document multi-file with `--manifest`
- [x] Document multi-file with `--filename-pattern`
- [x] Verify example commands run against samples

## Phase 4 — Bencher API guide

- [x] Create `docs/user/bencher-api.md`
- [x] Document `--bencher-project` requirement
- [x] Document `--bencher-url` for self-hosted instances
- [x] Document authentication via `BENCHER_API_TOKEN` and `--bencher-token`
- [x] Add placeholder project slug with substitution instructions

## Phase 5 — Config file and testbed decomposition guide

- [x] Create `docs/user/config.md` covering config file discovery
- [x] Document `--config FILE` option
- [x] Document precedence: defaults < config < flags
- [x] List all config keys with descriptions
- [x] Add example `ulv.toml` for ASV project
- [x] Create `docs/user/testbeds.md` covering `[testbeds]` table
- [x] Document `--testbeds-file` option
- [x] Document `--allow-unmapped` option
- [x] Add example decomposing testbeds into factors

## Phase 6 — CLI reference

- [x] Create `docs/user/cli-reference.md`
- [x] Document `ulv --version` and `ulv --help`
- [x] Document all `ulv build` flags with types and defaults
- [x] Document all `ulv serve` flags with types and defaults
- [x] Cross-check against `--help` output for completeness

## Phase 7 — Verification tests for documentation

- [x] Create `tests/test_docs.py`
- [x] Add test for quickstart command against ASV fixture
- [x] Add test for BMF sample command
- [x] Add test for config file parsing
- [x] Verify `make verify` passes with new tests

## Phase 8 — Index, cross-links, and polish

- [x] Update `docs/user/index.md` with complete table of contents
- [x] Add navigation links to each page
- [x] Review all pages for consistent style per `docs/style.md`
- [x] Verify no broken internal links
- [x] Final `make verify` pass
