# ASV Format

Visualize benchmark results from [Airspeed Velocity](https://asv.readthedocs.io/)
(ASV), the Python benchmarking tool.

## Directory layout

ASV stores results in a directory with this structure:

```
results/
  benchmarks.json           # benchmark metadata (names, params, units)
  <machine>/
    machine.json            # machine specs (arch, cpu, os, ram)
    <commit>-<env>.json     # result file per commit and environment
```

Each machine subdirectory contains a `machine.json` describing the hardware,
plus one or more result files named `<commit_hash>-<environment>.json`.

## Basic usage

Generate a site from ASV results:

```bash
uv run ulv build \
  -i asv \
  --input-dir path/to/results \
  -o path/to/output
```

Try it with the included test fixture:

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/asv-demo
```

## Setting the project name

Add a project name to the navbar:

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/asv-demo \
  --project "My Benchmarks"
```

Link the project name to a URL:

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/asv-demo \
  --project "My Project" \
  --project-url "https://github.com/myorg/myproject"
```

## Git enrichment

When you have a local clone of the benchmarked repository, ulv can enrich
results with commit ordering, dates, and branch attribution.

Point to the repository:

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/asv-demo \
  --repo /path/to/repo
```

Specify which branches to include:

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/asv-demo \
  --repo /path/to/repo \
  --branches main,release
```

## Commit links

Link commit hashes to your repository's web interface:

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/asv-demo \
  --show-commit-url "https://github.com/myorg/myproject/commit/"
```

Commit hashes in the UI become clickable links to the full URL
(e.g., `https://github.com/myorg/myproject/commit/abc123`).

## Next steps

- [Configuration](config.md) — Set these options in a config file
- [Testbed Decomposition](testbeds.md) — Compare results across machines
- [CLI Reference](cli-reference.md) — All available options
