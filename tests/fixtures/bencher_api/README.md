# Bencher API response fixtures

`reports.json` is a hand-modeled response for
`GET /v0/projects/demo/reports` (a JSON array of `JsonReport`),
shaped after the schemas in Bencher's published OpenAPI document
(`https://bencher.dev/download/openapi.json`, API version **0.6.8**,
retrieved 2026-07-06): `JsonReport` -> `branch.head.version
{number, hash}`, `testbed {name, slug}`, `start_time`, and
`results: [[JsonReportResult]]` with `benchmark`, `iteration`, and
`measures: [{measure {slug, units}, metric {value, lower_value,
upper_value}}]`. Not recorded from a live server; the transport seam
(ADR 0005) makes a recorded-against-live refresh a drop-in.

Contents: branch `main`, two versions (hashes `aa…`/`bb…`), two
testbeds (`linux-x64`, `macos-arm`), benchmarks `adapter::json`
(latency with bounds + throughput without) and `parser` (latency,
linux only).
