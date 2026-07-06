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

Generate a static HTML site from benchmark results.

```
ulv build [-h] [--config FILE] [-i INPUT_FORMAT] [--input-dir INPUT_DIR]
          [-o OUTPUT_DIR] [--project PROJECT] [--project-url PROJECT_URL]
          [--show-commit-url SHOW_COMMIT_URL] [--repo REPO]
          [--branches BRANCHES] [--manifest MANIFEST]
          [--filename-pattern FILENAME_PATTERN] [--commit COMMIT]
          [--date DATE] [--branch BRANCH] [--testbed TESTBED]
          [--testbeds-file FILE] [--allow-unmapped] [--bencher-url BENCHER_URL]
          [--bencher-project BENCHER_PROJECT] [--bencher-token BENCHER_TOKEN]
```

### General options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `-h`, `--help` | | | Show help message and exit |
| `--config FILE` | path | `./ulv.toml` | Config file (TOML, or JSON with `.json` suffix) |
| `-i`, `--input-format` | string | | Input format: `asv`, `bmf`, or `bencher-api` |
| `--input-dir` | path | | Directory containing benchmark data |
| `-o`, `--output-dir` | path | | Directory to write the generated site |

### Site branding

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--project` | string | `""` | Project name shown in the navbar |
| `--project-url` | string | `"#"` | URL the project name links to |
| `--show-commit-url` | string | `""` | URL prefix for commit links (hash appended) |

### Git enrichment (ASV)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--repo` | path | | Path to git repository for commit ordering and dates |
| `--branches` | string | | Comma-separated branches to attribute results to |

### BMF metadata

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--manifest` | path | | Sidecar manifest mapping filenames to metadata |
| `--filename-pattern` | string | | Filename template with `{commit}`, `{date}`, `{branch}`, `{testbed}` |
| `--commit` | string | | Commit hash for single BMF file |
| `--date` | string | | ISO 8601 date for single BMF file |
| `--branch` | string | | Branch name for single BMF file |
| `--testbed` | string | | Testbed name for single BMF file |

### Testbed decomposition

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--testbeds-file FILE` | path | | Testbed decomposition file (TOML or JSON) |
| `--allow-unmapped` | flag | `false` | Include unmapped testbeds with `unknown` factors |

### Bencher API

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--bencher-url` | URL | `https://api.bencher.dev` | Bencher server URL |
| `--bencher-project` | string | | Bencher project slug or UUID |
| `--bencher-token` | string | | API token (prefer `BENCHER_API_TOKEN` env var) |

## ulv serve

Serve a built site locally for preview. A development convenience only; the
generated site works with any static file server.

```
ulv serve [-h] [--config FILE] [--host HOST] [--port PORT] [directory]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `directory` | path | from config | Site directory to serve (positional) |
| `-h`, `--help` | | | Show help message and exit |
| `--config FILE` | path | `./ulv.toml` | Config file for `output_dir` fallback |
| `--host` | string | `127.0.0.1` | Host to bind |
| `--port` | integer | `8000` | Port to bind (0 picks a free port) |

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

- [Quickstart](quickstart.md) — Get started with ulv
- [Configuration](config.md) — Config file format and options
- [User Guide Index](index.md) — All documentation pages
