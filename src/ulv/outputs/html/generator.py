"""Static HTML site generator using the vendored ASV frontend.

Mirrors the output contract of asv's publish step (publish.py:283-310):
the vendored frontend boots from `info.json`, then `index.json`, then
fetches graph JSON files by recomputing paths client-side. The data
pipeline and the atomic build/swap live in `ulv.outputs.common`; this
module only supplies the vendored static tree and the snapshot page.
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


class HtmlOutputGenerator(HtmlSiteGeneratorBase):
    """Built-in `html` output generator."""

    name = "html"
    static_package = "ulv.outputs.html"

    def _write_snapshot(self, build_dir: Path, dataset: Dataset) -> None:
        """Non-time-series view for a lone snapshot (spec Decision 3):
        one table row per benchmark × measure (× testbed), values and
        bounds as-is, absent bounds as empty cells — never zero."""
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
                f'<p class="text-muted">commit '
                f"{html.escape(commit_hash)} {html.escape(when)}</p>"
            )

        title = html.escape(dataset.project or "benchmarks")
        page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="vendor/css/bootstrap.min.css">
</head>
<body>
<div class="container">
<h1>{title}</h1>
{subtitle}
<table class="table table-striped table-hover">
<thead><tr>{head}</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</div>
</body>
</html>
"""
        (build_dir / "snapshot.html").write_text(page)
        (build_dir / "index.html").write_text(snapshot_redirect_html())
