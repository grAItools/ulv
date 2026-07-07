# CLI Reference

Complete reference for all ulv commands and options.

## Global options

```
ulv [-h] [--version] {build,serve} ...
```

| Option | Description |
|--------|-------------|
| `-h`, `--help` | Show help message and exit |
| `--version` | Show program version and exit |

## ulv build

Read benchmark results and generate a static HTML site. Every flag below can also be set in the config file (snake_case key); flags win over the file.

```
ulv build [-h] [--config FILE] [--input-format INPUT_FORMAT] [--input-dir INPUT_DIR] [--output-dir OUTPUT_DIR] [--project PROJECT] [--project-url PROJECT_URL] [--show-commit-url SHOW_COMMIT_URL] [--repo REPO] [--branches BRANCHES] [--manifest MANIFEST] [--filename-pattern FILENAME_PATTERN] [--commit COMMIT] [--date DATE] [--branch BRANCH] [--testbed TESTBED] [--testbeds-file FILE] [--allow-unmapped] [--bencher-url BENCHER_URL] [--bencher-project BENCHER_PROJECT] [--bencher-token BENCHER_TOKEN]
```

### General options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-h`, `--help` | | | Show help message and exit |
| `--config` | string |  | config file (TOML, or JSON with a .json suffix); defaults to ./ulv.toml when present |
| `-i`, `--input-format` | string |  | input format name (e.g. 'asv') |
| `--input-dir` | string |  | directory containing the benchmark result data |
| `-o`, `--output-dir` | string |  | directory to write the generated site to |

### Site branding

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--project` | string |  | project name shown in the generated site |
| `--project-url` | string | `#` | URL the project name in the navbar links to |
| `--show-commit-url` | string |  | URL prefix for commit links (commit hash is appended) |

### Git enrichment (ASV)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--repo` | string |  | path to the project's git repository, enabling commit ordering, dates, tags, and branch enrichment |
| `--branches` | string |  | comma-separated branches to attribute results to (requires --repo; default: the repository's checked-out branch) |

### BMF metadata

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--manifest` | string |  | BMF sidecar manifest (JSON or TOML) mapping each input filename to its commit/date/branch/testbed metadata |
| `--filename-pattern` | string |  | BMF filename template with {commit}/{date}/{branch}/{testbed} fields, e.g. '{commit}_{date}.json' |
| `--commit` | string |  | commit hash for a single BMF input file |
| `--date` | string |  | ISO 8601 date for a single BMF input file |
| `--branch` | string |  | branch name for a single BMF input file |
| `--testbed` | string |  | testbed name for a single BMF input file |

### Testbed decomposition

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--testbeds-file` | string |  | testbed decomposition file (TOML, or JSON with a .json suffix) with top-level 'factors' and 'map' — the same shape as the [testbeds] config table, which it overrides |
| `--allow-unmapped` | flag | `false` | include testbeds missing from the [testbeds] mapping with 'unknown' factor values instead of failing |

### Bencher API

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--bencher-url` | string | `https://api.bencher.dev` | Bencher server URL for the bencher-api input (default: https://api.bencher.dev) |
| `--bencher-project` | string |  | Bencher project slug or UUID for the bencher-api input |
| `--bencher-token` | string |  | Bencher API token; prefer the BENCHER_API_TOKEN env var — a flag value lands in shell history |

## ulv serve

Serve a previously built site directory over HTTP. A development convenience only; the generated site needs nothing beyond a static file server.

```
ulv serve [-h] [directory] [--config FILE] [--host HOST] [--port PORT]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `directory` | string |  | site directory to serve (output of 'ulv build'); defaults to the config file's output_dir |
| `--config` | string |  | config file supplying output_dir when no directory is given; defaults to ./ulv.toml when present |
| `--host` | string | `127.0.0.1` | host to bind (default: 127.0.0.1) |
| `--port` | int | `8000` | port to bind; 0 picks a free port (default: 8000) |
| `-h`, `--help` | | | Show help message and exit |

## Environment variables

| Variable | Description |
|----------|-------------|
| `BENCHER_API_TOKEN` | Bencher API token (preferred over `--bencher-token`) |

## Examples

Build from ASV results:

```bash
uv run ulv build -i asv --input-dir .asv/results -o site
```

Build from BMF with manifest:

```bash
uv run ulv build -i bmf --input-dir results -o site --manifest manifest.json
```

Build from Bencher cloud:

```bash
export BENCHER_API_TOKEN="your-token"
uv run ulv build -i bencher-api --bencher-project my-project -o site
```

Serve a built site:

```bash
uv run ulv serve site
```

Use a config file:

```bash
uv run ulv build --config myproject.toml
```

## See also

- [Quickstart](quickstart.md) - Get started with ulv
- [Configuration](config.md) - Config file format and options
- [User Guide Index](index.md) - All documentation pages
