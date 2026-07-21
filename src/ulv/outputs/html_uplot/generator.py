"""Static HTML site generator with a self-authored uPlot frontend.

Emits the same data files as the vendored `html` generator — the
shared pipeline in `ulv.outputs.common` — under a frontend this
project owns end to end: plain ES modules and CSS plus a pinned uPlot
build (ADR 0008). The frontend locates every graph file through the
`graph_paths` manifest in `index.json` instead of recomputing
sanitized paths client-side.
"""

from __future__ import annotations

import html
from pathlib import Path

from ulv.model import Dataset
from ulv.outputs.common import (
    HtmlSiteGeneratorBase,
    snapshot_commit,
    snapshot_redirect_html,
    snapshot_table,
)


class HtmlUplotOutputGenerator(HtmlSiteGeneratorBase):
    """Built-in `html-uplot` output generator."""

    name = "html-uplot"
    static_package = "ulv.outputs.html_uplot"

    def _write_snapshot(self, build_dir: Path, dataset: Dataset) -> None:
        """Zero-JS snapshot page styled by the generator's own CSS:
        one table row per benchmark × measure (× testbed), absent
        bounds as empty cells — never zero."""
        headers, table_rows = snapshot_table(dataset)
        head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        rows = [
            "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>"
            for cells in table_rows
        ]

        subtitle = ""
        commit = snapshot_commit(dataset)
        if commit is not None:
            commit_hash, when = commit
            subtitle = (
                f'<p class="muted">commit '
                f"{html.escape(commit_hash)} {html.escape(when)}</p>"
            )

        title = html.escape(dataset.project or "benchmarks")
        page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="app.css">
</head>
<body class="snapshot">
<header class="site-header"><h1>{title}</h1></header>
<main class="content">
{subtitle}
<table class="data-table">
<thead><tr>{head}</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</main>
</body>
</html>
"""
        (build_dir / "snapshot.html").write_text(page)
        (build_dir / "index.html").write_text(snapshot_redirect_html())
