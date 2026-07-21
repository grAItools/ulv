# Configuration File

Use a TOML config file instead of passing options on the command line.

## Default config file

ulv looks for `./ulv.toml` in the current directory automatically. If found,
it loads settings from there without needing `--config`.

## Explicit config file

Specify a config file explicitly:

```bash
uv run ulv build --config path/to/myconfig.toml
```

JSON config files are also supported (detected by `.json` extension):

```bash
uv run ulv build --config path/to/config.json
```

## Precedence

Settings are merged in this order (later wins):

1. **Defaults** — built-in default values
2. **Config file** — values from `ulv.toml` or `--config`
3. **CLI flags** — command-line arguments

This lets you set common options in a config file and override specific
options on the command line.

## Example: ASV project

```toml
input_format = "asv"
input_dir = ".asv/results"
output_dir = "benchmark-site"
project = "My Project"
project_url = "https://github.com/myorg/myproject"
show_commit_url = "https://github.com/myorg/myproject/commit/"
repo = "."
branches = "main,release"
```

Build with just:

```bash
uv run ulv build
```

## Example: Bencher API

```toml
input_format = "bencher-api"
output_dir = "benchmark-site"
bencher_project = "my-project"
project = "My Project"
```

Set `BENCHER_API_TOKEN` in your environment, then:

```bash
uv run ulv build
```

## All config keys

| Key | Type | Description |
|-----|------|-------------|
| `input_format` | string | Input format: `asv`, `bmf`, or `bencher-api` |
| `input_dir` | string | Directory containing benchmark data |
| `output_dir` | string | Directory to write the generated site |
| `output_generator` | string | Frontend: `html` (vendored ASV UI, default) or `html-uplot` (lightweight uPlot UI); CLI flag: `--generator` |
| `project` | string | Project name shown in the navbar |
| `project_url` | string | URL the project name links to |
| `show_commit_url` | string | URL prefix for commit links |
| `repo` | string | Path to git repository for enrichment |
| `branches` | string | Comma-separated branch names |
| `manifest` | string | BMF manifest file path |
| `filename_pattern` | string | BMF filename pattern template |
| `commit` | string | Commit hash for single BMF file |
| `date` | string | ISO 8601 date for single BMF file |
| `branch` | string | Branch name for single BMF file |
| `testbed` | string | Testbed name for single BMF file |
| `allow_unmapped` | boolean | Allow unmapped testbeds (default: false) |
| `bencher_url` | string | Bencher server URL |
| `bencher_project` | string | Bencher project slug or UUID |
| `bencher_token` | string | Bencher API token (prefer env var) |

For testbed decomposition, see the `[testbeds]` table in
[Testbed Decomposition](testbeds.md).

## Next steps

- [Testbed Decomposition](testbeds.md) — Split testbeds into comparable factors
- [CLI Reference](cli-reference.md) — All available options
