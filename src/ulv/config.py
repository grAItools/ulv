"""Settings: config file plus CLI-flag overrides.

Precedence is defaults < config file < CLI flags (spec Decision 7; see
ADR 0004). The config file is TOML by default, JSON when the path ends
in `.json`; without `--config`, `./ulv.toml` is used when present.
Every settings field has a matching kebab-case CLI flag, and unknown or
mistyped config keys fail loudly naming the key and file.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path

from ulv.errors import UlvError

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
    for key, value in data.items():
        if key not in _FIELD_NAMES:
            known = ", ".join(sorted(_FIELD_NAMES))
            raise UlvError(
                f"unknown config key {key!r} in {path} (known keys: {known})",
                offending_input=str(path),
            )
        if not isinstance(value, str):
            raise UlvError(
                f"config key {key!r} in {path} must be a string, "
                f"got {type(value).__name__}",
                offending_input=str(path),
            )
    return data


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
