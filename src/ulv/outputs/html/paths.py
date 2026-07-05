"""Graph file paths, byte-compatible with the ASV frontend.

The vendored frontend recomputes these paths client-side
(asv.js:graph_to_path / escape_graph_parameter), so this module must
mirror asv/util.py:sanitize_filename and asv/graph.py:Graph.get_file_path
exactly — including the quirk that asv's character class escapes the
caret, so '^' is replaced while a backslash passes through. Verified
against values produced by asv's own code in tests/test_paths.py.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# Same pattern string as asv/util.py:1096.
_UNSAFE = re.compile('[<>:"/\\^|?*\x00-\x1f]')

_NTFS_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)


def sanitize_filename(filename: str) -> str:
    filename = _UNSAFE.sub("_", filename)
    if filename.upper() in _NTFS_RESERVED:
        filename += "_"
    return filename


def graph_path(params: Mapping[str, object], benchmark_name: str) -> str:
    """Relative path (no .json suffix) of one graph's data file.

    Each `key-value` part is a directory level; parts sort
    lexicographically, `None` renders as `key-null` and an empty value
    as the bare key (how `summary` and empty env params encode).
    """
    parts = []
    for key, value in params.items():
        if value is None:
            part = f"{key}-null"
        elif value:
            part = f"{key}-{value}"
        else:
            part = f"{key}"
        parts.append(sanitize_filename(str(part)))
    parts.sort()
    parts.insert(0, "graphs")
    parts.append(sanitize_filename(benchmark_name))
    return "/".join(parts)
