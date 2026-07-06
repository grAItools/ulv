"""User-supplied testbed decomposition (spec Decisions 8-9).

Bencher's flat testbed axis can be decomposed into independent factor
axes only via an explicit `[testbeds]` mapping in config — never by
parsing testbed names. A testbed missing from the mapping fails the
build naming every uncovered name; `allow_unmapped` instead includes
them with "unknown" for every declared factor plus a diagnostic. Any
input format with a testbed notion (bmf today, the Bencher API input
later) applies the same helpers.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from ulv.errors import UlvError

# Axes the pipeline itself owns: colliding factor names would corrupt
# filtering ('machine', 'testbed'), branch handling, or the summary
# graph path scheme, which reserves the 'summary' params key.
RESERVED_FACTOR_NAMES = frozenset({"machine", "branch", "testbed", "summary"})

UNKNOWN_VALUE = "unknown"


@dataclass(frozen=True)
class TestbedConfig:
    """Declared factor names plus the testbed -> factor-values table."""

    factors: tuple[str, ...]
    mapping: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]

    def factor_values(self, testbed: str) -> dict[str, str] | None:
        for name, entries in self.mapping:
            if name == testbed:
                return dict(entries)
        return None

    def covered(self) -> set[str]:
        return {name for name, _ in self.mapping}


def parse_testbeds(data, source) -> TestbedConfig:
    """Validate the raw `[testbeds]` table from a config file."""

    def fail(message: str) -> UlvError:
        return UlvError(
            f"invalid [testbeds] config in {source}: {message}",
            offending_input=str(source),
        )

    if not isinstance(data, dict):
        raise fail("expected a table with 'factors' and 'map'")
    unknown = set(data) - {"factors", "map"}
    if unknown:
        raise fail(f"unknown key(s) {sorted(unknown)}")

    factors = data.get("factors")
    if (
        not isinstance(factors, list)
        or not factors
        or not all(isinstance(f, str) for f in factors)
    ):
        raise fail("'factors' must be a non-empty list of factor names")
    if len(set(factors)) != len(factors):
        raise fail("'factors' contains duplicate names")
    reserved = sorted(set(factors) & RESERVED_FACTOR_NAMES)
    if reserved:
        raise fail(
            f"factor name(s) {reserved} are reserved axes and cannot be redeclared"
        )

    raw_map = data.get("map", {})
    if not isinstance(raw_map, dict):
        raise fail("'map' must be a table of testbed entries")
    declared = set(factors)
    mapping = []
    for testbed, entry in raw_map.items():
        if not isinstance(entry, dict):
            raise fail(f"entry for testbed {testbed!r} must be a table")
        missing = sorted(declared - set(entry))
        if missing:
            raise fail(
                f"entry for testbed {testbed!r} is missing declared factor(s) {missing}"
            )
        extra = sorted(set(entry) - declared)
        if extra:
            raise fail(
                f"entry for testbed {testbed!r} has undeclared factor(s) {extra}"
            )
        for factor, value in entry.items():
            if not isinstance(value, str):
                raise fail(
                    f"value for factor {factor!r} of testbed {testbed!r} "
                    f"must be a string"
                )
        mapping.append((testbed, tuple((factor, entry[factor]) for factor in factors)))
    return TestbedConfig(factors=tuple(factors), mapping=tuple(mapping))


def resolve_testbeds(
    names, config: TestbedConfig, allow_unmapped: bool
) -> dict[str, dict[str, str]]:
    """Factor dict per testbed name.

    Uncovered names fail by default, every one of them listed; with
    `allow_unmapped` they get UNKNOWN_VALUE for each declared factor and
    a stderr diagnostic still names them (spec Decision 9 — never
    silently mis-parsed or dropped).
    """
    names = sorted(set(names))
    uncovered = [name for name in names if config.factor_values(name) is None]
    if uncovered and not allow_unmapped:
        listed = ", ".join(uncovered)
        raise UlvError(
            f"testbed(s) not covered by the testbed mapping: {listed}; "
            f"add them to [testbeds.map] or pass --allow-unmapped",
            offending_input=listed,
        )

    resolved = {}
    for name in names:
        values = config.factor_values(name)
        if values is None:
            print(
                f"ulv: warning: testbed {name!r} is not covered by the "
                f"testbed mapping; using {UNKNOWN_VALUE!r} for factors "
                f"{', '.join(config.factors)}",
                file=sys.stderr,
            )
            values = dict.fromkeys(config.factors, UNKNOWN_VALUE)
        resolved[name] = values
    return resolved
