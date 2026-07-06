# Plan

## Architecture decisions

- **Documentation location:** `docs/user/` — a new subdirectory alongside the
  existing developer-facing docs. This keeps user content discoverable without
  polluting the root or mixing with ADRs. ADR: n/a (no new dependency or
  protocol).

- **Sample data strategy:** Reuse existing test fixtures for most examples
  (`tests/fixtures/asv_results/`, `tests/fixtures/bencher_api/`); add a minimal
  dedicated BMF sample under `docs/user/samples/` for the quickstart and BMF
  walkthrough where pedagogical clarity trumps fixture reuse. ADR: n/a.

- **Bencher cloud examples:** Use placeholder slugs (`YOUR_PROJECT`,
  `YOUR_TOKEN`) with explicit substitution instructions. No live server
  dependency. ADR: n/a.

- **Verification approach:** Markdown lint via `markdownlint-cli2` (the same
  tool style.md recommends for prose) plus command-block smoke tests that run
  the documented invocations against fixtures and assert exit 0 / expected
  outputs exist. ADR: n/a (no new runtime dependency; dev/test only).

## Phase 1 — Directory scaffold and quickstart

**Scope.** Create the `docs/user/` directory structure with an index page and a
runnable quickstart example. The quickstart uses the existing ASV fixture so
users can clone the repo and immediately run `ulv build` without downloading
external data.

**Steps.**
1. Create `docs/user/index.md` with a brief intro and table of contents linking
   to subsequent pages.
2. Create `docs/user/quickstart.md` with:
   - Prerequisites (Python 3.11+, `uv`).
   - Clone repo, install with `uv sync`.
   - Run `ulv build` against `tests/fixtures/asv_results/` producing a site in
     a temp directory.
   - Open the resulting `index.html` in a browser.
   - Run `ulv serve` to preview.
3. Confirm the exact command paths work by running them manually (no automated
   test yet).

**Tests.** `make verify` passes (no new code, only markdown). A manual run of
the quickstart commands succeeds.

**Exit criteria.** A user following `docs/user/quickstart.md` can build and
preview a site using only in-repo fixtures.

## Phase 2 — ASV format guide

**Scope.** Document the `asv` input format with complete invocation examples.

**Steps.**
1. Create `docs/user/asv.md` covering:
   - Expected directory layout (`benchmarks.json`, `<machine>/machine.json`,
     `<machine>/<commit>-<env>.json`).
   - Minimal `ulv build -i asv --input-dir ... -o ...` invocation.
   - Setting project name with `--project`.
   - Git enrichment with `--repo`, `--branches`, `--show-commit-url`.
2. Use the existing test fixture path in all examples so readers can run them.

**Tests.** `make verify` passes. Example commands in the doc run successfully
against `tests/fixtures/asv_results/`.

**Exit criteria.** The ASV guide covers all spec success criteria for that
format (runnable example, common options).

## Phase 3 — BMF format guide with dedicated sample

**Scope.** Document the `bmf` input format and provide a minimal sample dataset
under `docs/user/samples/` for clarity.

**Steps.**
1. Create `docs/user/samples/bmf/` with:
   - Two or three `.json` files representing distinct commits.
   - A `manifest.json` mapping filenames to commit/date/testbed metadata.
2. Create `docs/user/bmf.md` covering:
   - Bencher Metric Format structure (`{benchmark: {measure: {value, ...}}}`).
   - Single-file invocation with `--commit`, `--date`, `--testbed`.
   - Multi-file with `--manifest` (using the new sample).
   - Multi-file with `--filename-pattern` template.
3. Link to the BMF spec (bencher.dev) for canonical schema.

**Tests.** `make verify` passes. Example commands run successfully against the
new `docs/user/samples/bmf/` directory.

**Exit criteria.** The BMF guide covers all spec success criteria for that
format.

## Phase 4 — Bencher API guide

**Scope.** Document the `bencher-api` input format for fetching data from a
Bencher server.

**Steps.**
1. Create `docs/user/bencher-api.md` covering:
   - How the input fetches reports from a Bencher server.
   - Required `--bencher-project` (or config key).
   - Optional `--bencher-url` for self-hosted instances.
   - Authentication via `BENCHER_API_TOKEN` env var (preferred) or
     `--bencher-token` flag (discouraged for shell history).
2. Use placeholder project slug (`YOUR_PROJECT`) with explicit substitution
   note.
3. Mention the transport seam exists for testing but do not document it as a
   user-facing feature.

**Tests.** `make verify` passes. No live server required; commands shown with
placeholders.

**Exit criteria.** The Bencher API guide satisfies spec success criterion 4.

## Phase 5 — Config file and testbed decomposition guide

**Scope.** Document `ulv.toml` configuration and the testbed decomposition
feature.

**Steps.**
1. Create `docs/user/config.md` covering:
   - Default config file discovery (`./ulv.toml`).
   - Explicit `--config FILE`.
   - Precedence: defaults < config file < CLI flags.
   - Full list of config keys (mirror of CLI flags, snake_case).
   - Example `ulv.toml` for an ASV project.
2. Create `docs/user/testbeds.md` covering:
   - The `[testbeds]` table with `factors` and `map`.
   - `--testbeds-file` for standalone mapping.
   - `--allow-unmapped` for lenient mode.
   - Example decomposing `linux-x64`, `macos-arm` into `os` and `arch` factors.

**Tests.** `make verify` passes. Example config files parse without error when
fed to `ulv build --config`.

**Exit criteria.** Config file usage (spec criterion 8) and testbed
decomposition are documented.

## Phase 6 — CLI reference

**Scope.** Provide a complete API reference for all CLI commands and options.

**Steps.**
1. Create `docs/user/cli-reference.md` with:
   - `ulv --version`, `ulv --help`.
   - `ulv build` with every flag, type, default, and behavior.
   - `ulv serve` with every flag.
2. Organize by subcommand, then alphabetically by flag.
3. Keep descriptions concise; link to guides for context.

**Tests.** `make verify` passes. Cross-check against `ulv build --help` and
`ulv serve --help` output to ensure nothing is missing.

**Exit criteria.** Spec success criterion 5 (API reference) is satisfied.

## Phase 7 — Verification tests for documentation

**Scope.** Add automated smoke tests that execute the documented commands and
verify they produce expected outputs.

**Steps.**
1. Create `tests/test_docs.py` with:
   - A test that runs the quickstart command against
     `tests/fixtures/asv_results/` and asserts exit 0 and `index.html` exists.
   - A test that runs the BMF sample command against `docs/user/samples/bmf/`
     and asserts exit 0.
   - A test that parses each example `ulv.toml` snippet and asserts no config
     error.
2. Optionally add a `markdownlint` step to `make verify` if not already present
   (check existing Makefile first).

**Tests.** `make verify` passes including the new `test_docs.py` tests.

**Exit criteria.** Every runnable command in the documentation is covered by at
least one automated test.

## Phase 8 — Index, cross-links, and polish

**Scope.** Finalize the documentation structure with cross-links, consistent
style, and a complete index.

**Steps.**
1. Update `docs/user/index.md` with a complete table of contents and brief
   descriptions.
2. Add navigation links (prev/next or see-also) at the bottom of each page.
3. Review all pages for consistent voice, formatting, and adherence to
   `docs/style.md`.
4. Ensure no broken internal links (relative paths).

**Tests.** `make verify` passes. Manual review confirms navigation works.

**Exit criteria.** Documentation is polished, navigable, and ready for users.

## Risks & open questions

- **Test fixture stability:** If `tests/fixtures/asv_results/` changes in a
  future commit, quickstart commands may break. Mitigation: the doc tests in
  Phase 7 will catch this.

- **Bencher cloud access:** Users without Bencher accounts cannot run the
  bencher-api examples. Mitigation: placeholder approach with clear
  instructions; no live server dependency.

- **Markdown lint tooling:** If `markdownlint-cli2` is not in the dev
  dependencies, adding it requires a justification. Mitigation: make it
  optional or skip if the project prefers manual review.
