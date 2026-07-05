"""Plugin protocols and registries.

Input formats and output generators are pluggable (see ADR 0002): two
registries hold the built-ins, third parties add plugins either through
`importlib.metadata` entry points (groups `ulv.input_formats` and
`ulv.output_generators`) or programmatically via `Registry.register`.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path
from typing import Protocol, runtime_checkable

from ulv.errors import UlvError
from ulv.model import Dataset

INPUT_GROUP = "ulv.input_formats"
OUTPUT_GROUP = "ulv.output_generators"


@runtime_checkable
class InputFormat(Protocol):
    """Reads benchmark results from some source into a `Dataset`."""

    name: str

    def load(self, source, options) -> Dataset: ...


@runtime_checkable
class OutputGenerator(Protocol):
    """Renders a `Dataset` into an output directory."""

    name: str

    def generate(self, dataset: Dataset, out_dir: Path, options) -> None: ...


class Registry:
    """Name → plugin lookup for one entry-point group.

    Explicit `register()` calls always win: entry-point discovery runs
    lazily on first lookup and skips names that are already registered,
    so a broken third-party package can never shadow a built-in.
    """

    def __init__(self, entry_point_group: str):
        self._group = entry_point_group
        self._plugins: dict[str, object] = {}
        self._discovered = False

    def register(self, plugin) -> None:
        name = plugin.name
        if name in self._plugins:
            raise ValueError(f"plugin {name!r} is already registered")
        self._plugins[name] = plugin

    def get(self, name: str):
        self._discover()
        try:
            return self._plugins[name]
        except KeyError:
            known = ", ".join(sorted(self._plugins)) or "none"
            raise UlvError(
                f"unknown plugin {name!r} in group {self._group!r} "
                f"(available: {known})",
                offending_input=name,
            ) from None

    def names(self) -> list[str]:
        self._discover()
        return sorted(self._plugins)

    def _discover(self) -> None:
        if self._discovered:
            return
        self._discovered = True
        for entry_point in entry_points(group=self._group):
            if entry_point.name in self._plugins:
                continue
            loaded = entry_point.load()
            # An entry point may name a plugin class or a ready instance.
            self._plugins[entry_point.name] = (
                loaded() if isinstance(loaded, type) else loaded
            )


input_formats = Registry(INPUT_GROUP)
output_generators = Registry(OUTPUT_GROUP)
