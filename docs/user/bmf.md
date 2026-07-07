# BMF Format

Visualize benchmark results in
[Bencher Metric Format](https://bencher.dev/docs/reference/bencher-metric-format/)
(BMF), a simple JSON structure for recording benchmark measurements.

## BMF structure

Each BMF file contains benchmark results as a nested object:

```json
{
  "benchmark_name": {
    "measure_name": {
      "value": 12.5,
      "lower_value": 11.8,
      "upper_value": 13.2
    }
  }
}
```

- **benchmark_name** — identifies the benchmark (e.g., `parse_json`)
- **measure_name** — identifies what was measured (e.g., `latency`, `throughput`)
- **value** — the measured result (required)
- **lower_value** / **upper_value** — confidence interval bounds (optional)

A file can contain multiple benchmarks, each with multiple measures.

## Single-file mode

When you have exactly one BMF file, provide commit metadata on the command
line:

```bash
uv run ulv build \
  -i bmf \
  --input-dir /path/to/single-result \
  -o /tmp/bmf-demo \
  --commit a1b2c3d4 \
  --date 2026-01-15T10:00:00Z \
  --testbed linux-x64
```

This mode requires exactly one `.json` file in the input directory. For
multiple files, use a manifest or filename pattern.

## Multi-file with manifest

For multiple files with different commits, use a manifest file that maps
each filename to its metadata:

```json
{
  "commit-001.json": {
    "commit": "a1b2c3d4",
    "date": "2026-01-15T10:00:00Z",
    "testbed": "linux-x64"
  },
  "commit-002.json": {
    "commit": "e5f6a7b8",
    "date": "2026-01-16T14:30:00Z",
    "testbed": "linux-x64"
  }
}
```

Build with the manifest:

```bash
uv run ulv build \
  -i bmf \
  --input-dir docs/user/samples/bmf \
  -o /tmp/bmf-demo \
  --manifest docs/user/samples/bmf/manifest.json
```

Try it with the included sample:

```bash
uv run ulv build \
  -i bmf \
  --input-dir docs/user/samples/bmf \
  -o /tmp/bmf-demo \
  --manifest docs/user/samples/bmf/manifest.json
```

## Multi-file with filename pattern

If your filenames encode metadata, use a pattern template instead of a
manifest. The template uses placeholders for `{commit}`, `{date}`,
`{branch}`, and `{testbed}`:

```bash
uv run ulv build \
  -i bmf \
  --input-dir /path/to/results \
  -o /tmp/bmf-demo \
  --filename-pattern "{commit}_{date}.json"
```

For a file named `a1b2c3d4_2026-01-15.json`, this extracts:
- commit: `a1b2c3d4`
- date: `2026-01-15`

## Next steps

- [Bencher API](bencher-api.md) — Fetch BMF data from a Bencher server
- [Configuration](config.md) — Set these options in a config file
- [CLI Reference](cli-reference.md) — All available options
