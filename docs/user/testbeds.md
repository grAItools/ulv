# Testbed Decomposition

Split testbed names into independent factors for better comparison across
environments.

## The problem

Benchmark results often come from multiple testbeds like `linux-x64`,
`linux-arm64`, `macos-arm64`. Comparing across all testbeds at once can be
noisy. Decomposing testbeds into factors (`os`, `arch`) lets you filter by
one dimension while comparing another.

## The `[testbeds]` table

Add a `[testbeds]` section to your config file:

```toml
[testbeds]
factors = ["os", "arch"]

[testbeds.map.linux-x64]
os = "linux"
arch = "x64"

[testbeds.map.linux-arm64]
os = "linux"
arch = "arm64"

[testbeds.map.macos-arm64]
os = "macos"
arch = "arm64"
```

The `factors` list declares which axes you want. Each `[testbeds.map.<name>]`
entry maps a testbed name to its factor values.

## Validation rules

- Every testbed entry must have exactly the declared factors
- No extra or missing factors allowed
- Reserved names (`machine`, `branch`, `testbed`, `summary`) cannot be factors

## Standalone testbeds file

Keep the testbed mapping in a separate file with `--testbeds-file`:

```bash
uv run ulv build \
  -i bmf \
  --input-dir results \
  -o output \
  --testbeds-file testbeds.toml
```

The file contains just the `[testbeds]` table body:

```toml
factors = ["os", "arch"]

[map.linux-x64]
os = "linux"
arch = "x64"

[map.macos-arm64]
os = "macos"
arch = "arm64"
```

## Handling unmapped testbeds

By default, testbeds not in the mapping cause an error. To include them
anyway with `unknown` factor values:

```bash
uv run ulv build \
  -i bmf \
  --input-dir results \
  -o output \
  --testbeds-file testbeds.toml \
  --allow-unmapped
```

A warning is printed for each unmapped testbed.

## Example: multi-platform CI

With this config:

```toml
input_format = "bmf"
input_dir = "benchmark-results"
output_dir = "site"

[testbeds]
factors = ["os", "arch"]

[testbeds.map.ubuntu-latest-x64]
os = "linux"
arch = "x64"

[testbeds.map.ubuntu-latest-arm64]
os = "linux"
arch = "arm64"

[testbeds.map.macos-14]
os = "macos"
arch = "arm64"

[testbeds.map.windows-latest]
os = "windows"
arch = "x64"
```

The generated site shows `os` and `arch` as filter axes, letting you compare
all Linux results or all arm64 results independently.

## Next steps

- [Configuration](config.md) — Other config file options
- [CLI Reference](cli-reference.md) — All available options
