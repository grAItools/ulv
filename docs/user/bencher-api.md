# Bencher API

Fetch benchmark data directly from a [Bencher](https://bencher.dev/) server
and generate a visualization site.

## Prerequisites

- A Bencher account with at least one project containing benchmark reports
- An API token (from your Bencher account settings)

## Basic usage

Fetch data from Bencher cloud:

```bash
export BENCHER_API_TOKEN="your-api-token"
uv run ulv build \
  -i bencher-api \
  --bencher-project YOUR_PROJECT \
  -o /tmp/bencher-demo
```

Replace `YOUR_PROJECT` with your Bencher project slug or UUID.

## Authentication

Provide your API token via environment variable (recommended):

```bash
export BENCHER_API_TOKEN="your-api-token"
```

Alternatively, pass it as a flag (not recommended for shell history):

```bash
uv run ulv build \
  -i bencher-api \
  --bencher-project YOUR_PROJECT \
  --bencher-token "your-api-token" \
  -o /tmp/bencher-demo
```

## Self-hosted Bencher

For a self-hosted Bencher instance, specify the server URL:

```bash
export BENCHER_API_TOKEN="your-api-token"
uv run ulv build \
  -i bencher-api \
  --bencher-url "https://bencher.your-company.com" \
  --bencher-project YOUR_PROJECT \
  -o /tmp/bencher-demo
```

The default URL is `https://api.bencher.dev` (Bencher cloud).

## Finding your project slug

Your project slug appears in Bencher URLs:

```
https://bencher.dev/console/projects/YOUR_PROJECT/perf
                                   ^^^^^^^^^^^^
```

You can also use the project UUID from the Bencher API or console.

## Next steps

- [Configuration](config.md) — Store Bencher settings in a config file
- [CLI Reference](cli-reference.md) — All available options
