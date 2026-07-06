# User Documentation

## Problem

Unladen Velocity (ulv) users currently have no guided documentation showing
how to use the tool in practice. The README is developer-focused (make
commands, agent conventions), and the architecture docs describe internal
structure rather than end-user workflows. A new user wanting to visualize
benchmark data must reverse-engineer CLI options from `--help` output, read
source code to understand input format requirements, and experiment to
discover working invocations. This learning curve delays adoption and
increases support burden.

## Goal

Users can follow worked examples in `/docs/user/` to generate and view
benchmark visualizations from ASV results, Bencher Metric Format files, or
Bencher cloud data without consulting source code.

## Users & stakeholders

- **Primary users:** Developers with benchmark data who want to visualize
  trends over time using ulv.
- **Secondary users:** CI/CD engineers integrating ulv into automated
  pipelines.
- **Stakeholders:** Maintainers responsible for user support.

## Success criteria

1. **Quickstart example runs end-to-end.** A user can clone the repo, run
   the documented quickstart command against included sample data, and open
   the resulting HTML site in a browser.

2. **Each input format has a runnable example.** The documentation includes
   at least one complete `ulv build` invocation for each supported input
   format (asv, bmf, bencher-api), using either bundled sample datasets or
   documented external sources.

3. **Common options are demonstrated.** Examples show how to set project
   name, enable git enrichment with branches and tags, configure commit
   links, and decompose testbeds into factors.

4. **Bencher cloud integration is documented.** A dedicated section shows
   how to fetch data from a Bencher server, including authentication via
   environment variable and project selection.

5. **API reference exists.** A reference section documents all CLI commands,
   subcommands, and options with their types, defaults, and behaviors.

6. **Sample datasets are provided when needed.** If runnable examples require
   sample data not already present in the repo, that data is added under a
   documented location (e.g., `docs/user/samples/` or repurposed test
   fixtures).

7. **Preview workflow is documented.** The `ulv serve` command is explained
   as a local preview mechanism, with an example invocation.

8. **Config file usage is documented.** At least one example shows
   `ulv.toml` configuration as an alternative to CLI flags.

## Non-goals

- **Plugin development guide.** Documenting how to write custom input or
  output plugins is out of scope; the plugin protocol is internal API.

- **Contributor/developer documentation.** Docs on testing, style, ADRs,
  and CI remain under `/docs/` and are not part of user documentation.

- **Tutorial video or interactive walkthrough.** Text-based documentation
  only.

- **Regression detection documentation.** The step-detection feature is
  explicitly deferred (spec Decision 6); documenting placeholders or
  null behaviors is out of scope.

- **Hosted documentation site.** The docs are markdown files in the repo,
  not a generated site (e.g., MkDocs, Sphinx).

## Open questions

1. **Sample data placement.** Should user-documentation examples reuse
   existing test fixtures (e.g., `tests/fixtures/asv_results/`), or should
   a separate `docs/user/samples/` directory contain purpose-built minimal
   examples? Reuse reduces duplication; dedicated samples can be more
   pedagogically clear.

2. **Bencher cloud example project.** The bencher-api examples need a
   publicly accessible project on the Bencher cloud instance. Is there a
   known public project to reference, or should examples use a placeholder
   project slug with instructions for users to substitute their own?
