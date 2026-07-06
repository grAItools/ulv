"""Settings: config file plus CLI-flag overrides.

Precedence is defaults < config file < CLI flags (spec Decision 7; see
ADR 0004). The config file is TOML by default, JSON when the path ends
in `.json`; without `--config`, `./ulv.toml` is used when present.
Every scalar settings field has a matching kebab-case CLI flag; the
structured `[testbeds]` table is overridden by `--testbeds-file`, which
names a file with the same table body. Unknown or mistyped config keys
fail loudly naming the key and file.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

from ulv.errors import UlvError
from ulv.testbeds import TestbedConfig, parse_testbeds

DEFAULT_CONFIG_NAME = "ulv.toml"


@dataclass(frozen=True)
class Settings:
    """Flat, typed settings. `None` means "not configured" for values
    that have no usable default and must come from a flag or the file."""

    input_format: str | None = None
    input_dir: str | None = None
    output_dir: str | None = None
    project: str = ""
    project_url: str = "#"
    show_commit_url: str = ""
    # Optional git enrichment (spec Decision 4). `branches` is a
    # comma-separated list — config values stay plain strings so the
    # file and the flag share one spelling.
    repo: str | None = None
    branches: str = ""
    # BMF sidecar metadata (spec Decision 3): a manifest file or a
    # filename pattern for many files, or per-file values for a single
    # file. Ordering never comes from file order or timestamps.
    manifest: str | None = None
    filename_pattern: str | None = None
    commit: str | None = None
    date: str | None = None
    branch: str | None = None
    testbed: str | None = None
    # Testbed decomposition (spec Decisions 8-9): a structured
    # [testbeds] table (overridden by --testbeds-file, since a table
    # doesn't fit a flag value), plus the opt-in for testbeds the
    # mapping does not cover.
    testbeds: TestbedConfig | None = None
    allow_unmapped: bool = False
    # Bencher REST API source (spec Decision 1; ADR 0005). The token
    # can also come from the BENCHER_API_TOKEN env var.
    bencher_url: str = "https://api.bencher.dev"
    bencher_project: str | None = None
    bencher_token: str | None = None

    def branch_list(self) -> list[str]:
        return [name.strip() for name in self.branches.split(",") if name.strip()]


_FIELD_NAMES = {field.name for field in fields(Settings)}


def _parse_config(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise UlvError(
            f"cannot read config file {path}: {exc}", offending_input=str(path)
        ) from exc
    try:
        if path.suffix == ".json":
            data = json.loads(raw)
        else:
            data = tomllib.loads(raw.decode())
    except (ValueError, UnicodeDecodeError) as exc:
        # tomllib.TOMLDecodeError and json.JSONDecodeError are ValueErrors
        raise UlvError(
            f"malformed config file {path}: {exc}", offending_input=str(path)
        ) from exc
    if not isinstance(data, dict):
        raise UlvError(
            f"config file {path} must contain a table/object at the top level",
            offending_input=str(path),
        )
    return data


def _validate(data: dict, path: Path) -> dict:
    validated = {}
    for key, value in data.items():
        if key not in _FIELD_NAMES:
            known = ", ".join(sorted(_FIELD_NAMES))
            raise UlvError(
                f"unknown config key {key!r} in {path} (known keys: {known})",
                offending_input=str(path),
            )
        if key == "testbeds":
            validated[key] = parse_testbeds(value, path)
        elif key == "allow_unmapped":
            if not isinstance(value, bool):
                raise UlvError(
                    f"config key 'allow_unmapped' in {path} must be a "
                    f"boolean, got {type(value).__name__}",
                    offending_input=str(path),
                )
            validated[key] = value
        elif not isinstance(value, str):
            raise UlvError(
                f"config key {key!r} in {path} must be a string, "
                f"got {type(value).__name__}",
                offending_input=str(path),
            )
        else:
            validated[key] = value
    return validated


def load_settings(config_path, flag_overrides: dict) -> Settings:
    """Merge defaults, the config file, and CLI flags into `Settings`.

    `flag_overrides` maps field names to flag values; `None` means the
    flag was not passed and must not mask a config-file value.
    """
    file_values: dict = {}
    if config_path is not None:
        path = Path(config_path)
        if not path.is_file():
            raise UlvError(f"config file not found: {path}", offending_input=str(path))
        file_values = _validate(_parse_config(path), path)
    else:
        default = Path(DEFAULT_CONFIG_NAME)
        if default.is_file():
            file_values = _validate(_parse_config(default), default)

    merged = dict(file_values)
    merged.update(
        {key: value for key, value in flag_overrides.items() if value is not None}
    )
    return replace(Settings(), **merged)
