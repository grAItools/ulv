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
import importlib.resources
import shutil
from pathlib import Path

from ulv.model import Dataset
from ulv.outputs.common import (
    atomic_site_build,
    snapshot_commit,
    snapshot_table,
    write_site_data,
)


class HtmlUplotOutputGenerator:
    """Built-in `html-uplot` output generator."""

    name = "html-uplot"

    def generate(self, dataset: Dataset, out_dir, options) -> None:
        out_dir = Path(out_dir)
        options = options or {}

        def populate(build_dir: Path) -> None:
            self._copy_static(build_dir)
            (build_dir / "graphs").mkdir(exist_ok=True)
            self._write_site_json(build_dir, dataset, options)

        atomic_site_build(out_dir, populate)

    def _copy_static(self, build_dir: Path) -> None:
        static_root = importlib.resources.files("ulv.outputs.html_uplot") / "static"
        with importlib.resources.as_file(static_root) as static_path:
            shutil.copytree(static_path, build_dir)

    def _write_site_json(self, build_dir: Path, dataset: Dataset, options) -> None:
        if not dataset.has_time_axis:
            # A single revision has no history to graph: the site
            # becomes a static table and index.html a redirect, so the
            # entry point is index.html either way.
            self._write_snapshot(build_dir, dataset)
            return
        write_site_data(build_dir, dataset, options)

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
        redirect = (
            '<!doctype html>\n<html>\n<head>\n<meta charset="utf-8">\n'
            '<meta http-equiv="refresh" content="0; url=snapshot.html">\n'
            "</head>\n<body>\n"
            '<a href="snapshot.html">Benchmark snapshot</a>\n'
            "</body>\n</html>\n"
        )
        (build_dir / "index.html").write_text(redirect)
