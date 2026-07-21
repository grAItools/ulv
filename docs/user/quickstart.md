# Quickstart

Build and preview a benchmark visualization site in under five minutes.

## Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) package manager

## Clone and install

```bash
git clone https://github.com/grAItools/ulv.git
cd ulv
uv sync
```

## Build a site

The repository includes sample ASV benchmark data under `tests/fixtures/asv_results/`.
Generate a site from it:

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/ulv-quickstart
```

This produces a static HTML site in `/tmp/ulv-quickstart/`.

## Open in a browser

Open the generated site directly:

```bash
open /tmp/ulv-quickstart/index.html    # macOS
xdg-open /tmp/ulv-quickstart/index.html  # Linux
```

## Preview with the built-in server

For a more realistic preview, use the built-in HTTP server:

```bash
uv run ulv serve /tmp/ulv-quickstart
```

Then open <http://127.0.0.1:8000> in your browser.

Press `Ctrl+C` to stop the server.

## Choosing a frontend

By default the site ships the classic ASV browsing UI (the `html`
generator). A second, lightweight mobile-friendly frontend built on
uPlot is available as `html-uplot` (under 100 KB of frontend assets):

```bash
uv run ulv build \
  -i asv \
  --input-dir tests/fixtures/asv_results \
  -o /tmp/ulv-quickstart-uplot \
  --generator html-uplot
uv run ulv serve /tmp/ulv-quickstart-uplot
```

The vendored ASV frontend remains the default; builds without
`--generator` are unchanged. The same choice is available as the
`output_generator` key in the [config file](config.md).

## Next steps

- [ASV Format](asv.md) — Learn how to use your own ASV benchmark results
- [BMF Format](bmf.md) — Visualize Bencher Metric Format files
- [Configuration](config.md) — Use a config file instead of CLI flags
