"""Bencher Metric Format reader.

Parses BMF JSON (`{benchmark: {measure: {value, lower_value?,
upper_value?}}}`) from a single file or a directory of `.json` files.
Each (benchmark, measure) pair becomes one internal benchmark named
`<benchmark> (<measure>)` with the measure slug as its unit; bounds map
to `ResultPoint.lower`/`upper` and stay None when absent.

History ordering comes exclusively from explicit sidecar metadata
(spec Decision 3) — a manifest file, a `filename_pattern` template, or
per-file CLI flags for a single file. Never file order, name order, or
mtime. A lone file may omit metadata entirely and renders as a
non-time-series snapshot.

BMF carries no machine/environment data; each point lands in one
environment per `testbed` metadata value (a single opaque factor —
user-supplied decomposition into independent factors layers on top of
this seam).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import tomllib
from pathlib import Path

from ulv.errors import UlvError
from ulv.model import (
    Benchmark,
    Dataset,
    Environment,
    ResultPoint,
    ResultSeries,
    Revision,
)
from ulv.testbeds import resolve_testbeds

_METADATA_FIELDS = ("commit", "date", "branch", "testbed")
_METRIC_FIELDS = {"value", "lower_value", "upper_value"}

# Environment id when no testbed metadata is supplied.
_DEFAULT_ENV = "bencher"

# Revision id for a lone metadata-less snapshot.
_SNAPSHOT_ID = "snapshot"


def _load_json(path: Path):
    try:
        text = path.read_text()
    except OSError as exc:
        raise UlvError(f"cannot read {path}: {exc}", offending_input=str(path)) from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise UlvError(
            f"malformed JSON in {path}: {exc}", offending_input=str(path)
        ) from exc


def _parse_date(value, path: Path) -> dt.datetime:
    """ISO 8601 (naive treated as UTC) or a JS millisecond timestamp."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return dt.datetime.fromtimestamp(value / 1000, tz=dt.UTC)
    if isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value)
        except ValueError as exc:
            raise UlvError(
                f"invalid date {value!r} for {path}: {exc}",
                offending_input=str(path),
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.UTC)
        return parsed.astimezone(dt.UTC)
    raise UlvError(
        f"invalid date {value!r} for {path}: expected an ISO 8601 string "
        f"or a millisecond timestamp",
        offending_input=str(path),
    )


def _numeric(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_bmf(path: Path) -> dict[tuple[str, str], ResultPoint]:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise UlvError(
            f"BMF file {path} must contain a JSON object of benchmarks",
            offending_input=str(path),
        )
    points: dict[tuple[str, str], ResultPoint] = {}
    for benchmark, measures in data.items():
        if not isinstance(measures, dict):
            raise UlvError(
                f"benchmark {benchmark!r} in {path} must map measures to "
                f"metric objects",
                offending_input=str(path),
            )
        for measure, metric in measures.items():
            if not isinstance(metric, dict):
                raise UlvError(
                    f"measure {measure!r} of benchmark {benchmark!r} in "
                    f"{path} must be a metric object",
                    offending_input=str(path),
                )
            if "value" not in metric or not _numeric(metric["value"]):
                raise UlvError(
                    f"measure {measure!r} of benchmark {benchmark!r} in "
                    f"{path} needs a numeric 'value'",
                    offending_input=str(path),
                )
            for bound in ("lower_value", "upper_value"):
                if bound in metric and not _numeric(metric[bound]):
                    raise UlvError(
                        f"measure {measure!r} of benchmark {benchmark!r} in "
                        f"{path} has a non-numeric {bound!r}",
                        offending_input=str(path),
                    )
            extra = {k: v for k, v in metric.items() if k not in _METRIC_FIELDS}
            points[(benchmark, measure)] = ResultPoint(
                value=metric["value"],
                lower=metric.get("lower_value"),
                upper=metric.get("upper_value"),
                extra=extra,
            )
    return points


def _load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise UlvError(f"manifest file not found: {path}", offending_input=str(path))
    if path.suffix == ".toml":
        try:
            data = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise UlvError(
                f"malformed manifest {path}: {exc}", offending_input=str(path)
            ) from exc
    else:
        data = _load_json(path)
    if not isinstance(data, dict):
        raise UlvError(
            f"manifest {path} must map BMF filenames to metadata tables",
            offending_input=str(path),
        )
    for filename, entry in data.items():
        if not isinstance(entry, dict):
            raise UlvError(
                f"manifest entry {filename!r} in {path} must be a table",
                offending_input=str(path),
            )
    return data


def _pattern_regex(pattern: str) -> re.Pattern:
    regex = ""
    seen: set[str] = set()
    for part in re.split(r"(\{[a-z_]+\})", pattern):
        if part.startswith("{") and part.endswith("}"):
            field = part[1:-1]
            if field not in _METADATA_FIELDS:
                known = ", ".join(_METADATA_FIELDS)
                raise UlvError(
                    f"unknown field {field!r} in filename_pattern "
                    f"{pattern!r} (known fields: {known})"
                )
            if field in seen:
                raise UlvError(
                    f"field {field!r} appears more than once in "
                    f"filename_pattern {pattern!r}"
                )
            seen.add(field)
            regex += f"(?P<{field}>.+?)"
        else:
            regex += re.escape(part)
    return re.compile(regex + r"\Z")


class BmfInputFormat:
    """Built-in `bmf` input format (Bencher Metric Format files)."""

    name = "bmf"

    def load(self, source, options) -> Dataset:
        options = options or {}
        if options.get("repo"):
            raise UlvError(
                "git enrichment is not supported for the 'bmf' input yet; "
                "remove the 'repo' setting or order results via metadata "
                "dates"
            )
        if options.get("branches"):
            raise UlvError(
                "'branches' is not supported for the 'bmf' input; branch "
                "metadata comes from the sidecar (manifest, "
                "filename_pattern, or --branch)"
            )
        source = Path(source)
        files = self._collect_files(source, options)
        metadata = self._resolve_metadata(files, options)

        # With a decomposition configured, every testbed's factor dict is
        # settled up front so uncovered names fail before any building
        # (spec Decision 9: all of them listed, no site emitted).
        testbed_config = options.get("testbeds")
        factors_by_testbed: dict[str, dict[str, str]] | None = None
        if testbed_config is not None:
            testbed_names = {
                meta["testbed"] for meta in metadata.values() if meta.get("testbed")
            }
            factors_by_testbed = resolve_testbeds(
                testbed_names, testbed_config, bool(options.get("allow_unmapped"))
            )

        revisions: dict[str, Revision] = {}
        environments: dict[str, Environment] = {}
        benchmarks: dict[str, Benchmark] = {}
        series_points: dict[tuple[str, str], dict[str, ResultPoint]] = {}

        for path in files:
            meta = metadata[path.name]
            revision_id = meta.get("commit") or _SNAPSHOT_ID
            candidate = Revision(
                id=revision_id,
                commit_hash=meta.get("commit"),
                date=meta.get("date"),
                branch=meta.get("branch"),
            )
            existing = revisions.get(revision_id)
            if existing is None:
                revisions[revision_id] = candidate
            elif existing != candidate:
                raise UlvError(
                    f"conflicting metadata for commit {revision_id!r}: "
                    f"{path.name} disagrees with an earlier file "
                    f"(date/branch must match for a shared commit)",
                    offending_input=str(path),
                )
            testbed = meta.get("testbed")
            env_id = testbed or _DEFAULT_ENV
            if env_id not in environments:
                extra = {}
                if testbed and factors_by_testbed is not None:
                    factors = factors_by_testbed[testbed]
                    extra = {"testbed": testbed}
                elif testbed:
                    factors = {"testbed": testbed}
                else:
                    factors = {}
                environments[env_id] = Environment(
                    id=env_id, factors=factors, extra=extra
                )

            for (bench, measure), point in _parse_bmf(path).items():
                name = f"{bench} ({measure})"
                if name not in benchmarks:
                    benchmarks[name] = Benchmark(
                        name=name,
                        unit=measure,
                        pretty_name=name,
                        extra={"bmf_benchmark": bench, "bmf_measure": measure},
                    )
                series_points.setdefault((name, env_id), {})[revision_id] = point

        ordered = sorted(
            revisions.values(),
            key=lambda r: (
                r.date or dt.datetime.fromtimestamp(0, tz=dt.UTC),
                r.id,
            ),
        )
        return Dataset(
            project=options.get("project", ""),
            revisions=tuple(ordered),
            environments=tuple(environments[eid] for eid in sorted(environments)),
            benchmarks=benchmarks,
            series=tuple(
                ResultSeries(benchmark=bench, environment=env_id, points=pts)
                for (bench, env_id), pts in sorted(series_points.items())
            ),
        )

    def _collect_files(self, source: Path, options) -> list[Path]:
        manifest = options.get("manifest")
        manifest_path = Path(manifest).resolve() if manifest else None
        if source.is_file():
            return [source]
        if source.is_dir():
            files = [
                path
                for path in sorted(source.glob("*.json"))
                if manifest_path is None or path.resolve() != manifest_path
            ]
            if not files:
                raise UlvError(
                    f"no BMF .json files found in {source}",
                    offending_input=str(source),
                )
            return files
        raise UlvError(f"BMF input not found: {source}", offending_input=str(source))

    def _resolve_metadata(self, files: list[Path], options) -> dict[str, dict]:
        """Per-file metadata dicts (parsed date, commit, branch, testbed).

        The manifest or filename pattern supplies the base entry per
        file; single-file CLI flags then override individual fields
        (Decision 7: flags always win). Multi-file input where any file
        lacks metadata is an error naming that file — ordering is never
        inferred from file order or timestamps.
        """
        flag_meta = {
            field: options.get(field)
            for field in _METADATA_FIELDS
            if options.get(field) is not None
        }
        manifest = options.get("manifest")
        pattern = options.get("filename_pattern")

        if flag_meta and len(files) > 1:
            flags = ", ".join(sorted(flag_meta))
            raise UlvError(
                f"per-file metadata flags ({flags}) apply to a single BMF "
                f"file, but {len(files)} files were found; use a manifest "
                f"or filename_pattern instead"
            )

        raw: dict[str, dict] = {}
        if manifest:
            manifest_path = Path(manifest)
            entries = _load_manifest(manifest_path)
            known = {path.name for path in files}
            for filename in entries:
                if filename not in known:
                    raise UlvError(
                        f"manifest entry {filename!r} in {manifest_path} "
                        f"does not match any input file",
                        offending_input=filename,
                    )
            for path in files:
                if path.name not in entries:
                    raise UlvError(
                        f"no manifest entry for {path.name} in {manifest_path}",
                        offending_input=str(path),
                    )
                raw[path.name] = dict(entries[path.name])
        elif pattern:
            regex = _pattern_regex(pattern)
            for path in files:
                match = regex.fullmatch(path.name)
                if match is None:
                    raise UlvError(
                        f"{path.name} does not match filename_pattern {pattern!r}",
                        offending_input=str(path),
                    )
                raw[path.name] = match.groupdict()
        elif len(files) == 1:
            # A lone snapshot needs no ordering, so metadata is optional.
            raw[files[0].name] = {}
        else:
            raise UlvError(
                f"multiple BMF files but no ordering metadata; provide a "
                f"manifest, a filename_pattern, or per-file flags "
                f"(first file: {files[0]})",
                offending_input=str(files[0]),
            )

        # Flags beat the file-level source per key (Decision 7); the
        # multi-file guard above means they only ever apply to one file.
        if flag_meta:
            raw[files[0].name].update(flag_meta)

        require_ordering = len(files) > 1
        return {
            name: self._normalize(entry, files[0].parent / name, require_ordering)
            for name, entry in raw.items()
        }

    def _normalize(self, entry: dict, path: Path, require_ordering: bool) -> dict:
        unknown = set(entry) - set(_METADATA_FIELDS)
        if unknown:
            raise UlvError(
                f"unknown metadata key(s) {sorted(unknown)} for {path.name}",
                offending_input=str(path),
            )
        meta = dict(entry)
        if "date" in meta:
            meta["date"] = _parse_date(meta["date"], path)
        # Commit and date only matter when several files must be ordered;
        # a lone snapshot may carry any subset (or none) of the fields.
        if require_ordering and ("commit" not in meta or "date" not in meta):
            raise UlvError(
                f"metadata for {path.name} needs both 'commit' and 'date' "
                f"(got: {sorted(meta)})",
                offending_input=str(path),
            )
        return meta
