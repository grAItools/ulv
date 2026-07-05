"""Tests for optional git enrichment of the ASV input (src/ulv/gitrepo.py).

A synthetic repository is built per test session with commit dates
crafted so that date order differs from topological order, and a tiny
ASV results tree is generated at runtime from the repo's real hashes —
the same result set is then loaded with and without the repository
(spec: both cases on one result set).
"""

import json
import os
import subprocess

import pytest

from ulv.cli import main
from ulv.errors import UlvError
from ulv.inputs.asv import AsvInputFormat
from ulv.outputs.html.generator import HtmlOutputGenerator

# Deterministic, user-config-proof git environment.
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "ulv-test",
    "GIT_AUTHOR_EMAIL": "ulv-test@example.org",
    "GIT_COMMITTER_NAME": "ulv-test",
    "GIT_COMMITTER_EMAIL": "ulv-test@example.org",
    "GIT_TERMINAL_PROMPT": "0",
}

# Committer dates: A is the OLDEST commit topologically but has the
# NEWEST date, so date order (B, A) != topo order (A, B).
DATE_A = "2026-03-01T12:00:00 +0000"
DATE_B = "2026-01-01T12:00:00 +0000"
DATE_C = "2026-02-01T12:00:00 +0000"

# Result-file dates (JS ms) also make plain date ordering yield (B, A).
RESULT_DATE_A = 1772000000000
RESULT_DATE_B = 1767000000000
RESULT_DATE_C = 1770000000000


def _git(repo, *args, date=None):
    env = dict(os.environ, **GIT_ENV)
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """main: A -> B (tagged v1 at A); feat: A -> C."""
    path = tmp_path_factory.mktemp("repo")
    _git(path, "init", "-q", "-b", "main")
    (path / "f.txt").write_text("a")
    _git(path, "add", "f.txt")
    _git(path, "commit", "-q", "-m", "A", date=DATE_A)
    commit_a = _git(path, "rev-parse", "HEAD")
    _git(path, "tag", "v1")
    (path / "f.txt").write_text("b")
    _git(path, "commit", "-q", "-am", "B", date=DATE_B)
    commit_b = _git(path, "rev-parse", "HEAD")
    _git(path, "checkout", "-q", "-b", "feat", commit_a)
    (path / "f.txt").write_text("c")
    _git(path, "commit", "-q", "-am", "C", date=DATE_C)
    commit_c = _git(path, "rev-parse", "HEAD")
    _git(path, "checkout", "-q", "main")
    return {"path": path, "A": commit_a, "B": commit_b, "C": commit_c}


def _result_file(commit, date, value):
    return {
        "commit_hash": commit,
        "date": date,
        "env_name": "py3",
        "env_vars": {},
        "params": {"machine": "box", "python": "3.11"},
        "python": "3.11",
        "requirements": {},
        "result_columns": ["result", "params"],
        "results": {"time_x": [[value], []]},
        "durations": {},
        "version": 2,
    }


@pytest.fixture(scope="module")
def results_dir(tmp_path_factory, repo):
    root = tmp_path_factory.mktemp("results")
    (root / "benchmarks.json").write_text(
        json.dumps(
            {
                "time_x": {
                    "name": "time_x",
                    "param_names": [],
                    "params": [],
                    "type": "time",
                    "unit": "seconds",
                },
                "version": 2,
            }
        )
    )
    box = root / "box"
    box.mkdir()
    (box / "machine.json").write_text(
        json.dumps({"machine": "box", "os": "Linux", "version": 1})
    )
    for commit, date, value in [
        (repo["A"], RESULT_DATE_A, 1.0),
        (repo["B"], RESULT_DATE_B, 2.0),
        (repo["C"], RESULT_DATE_C, 3.0),
    ]:
        (box / f"{commit[:8]}-py3.json").write_text(
            json.dumps(_result_file(commit, date, value))
        )
    return root


def _load(results_dir, **options):
    return AsvInputFormat().load(results_dir, {"project": "demo", **options})


class TestWithoutRepo:
    def test_orders_by_result_date(self, results_dir, repo):
        dataset = _load(results_dir)
        assert [r.id for r in dataset.revisions] == [
            repo["B"],
            repo["C"],
            repo["A"],
        ]

    def test_no_branches_or_tags(self, results_dir):
        dataset = _load(results_dir)
        for revision in dataset.revisions:
            assert revision.branches == ()
            assert revision.tags == ()


@pytest.fixture(scope="module")
def dataset(results_dir, repo):
    return _load(results_dir, repo=str(repo["path"]), branches=["main", "feat"])


class TestWithRepo:
    def test_orders_by_topology_not_date(self, dataset, repo):
        assert [r.id for r in dataset.revisions] == [
            repo["A"],
            repo["B"],
            repo["C"],
        ]

    def test_dates_come_from_commits_not_results(self, dataset, repo):
        expected = {
            commit: int(_git(repo["path"], "log", "-1", "--format=%ct", commit))
            for commit in (repo["A"], repo["B"], repo["C"])
        }
        for revision in dataset.revisions:
            assert revision.date.timestamp() == expected[revision.id]

    def test_branch_membership_per_configured_branch(self, dataset, repo):
        by_id = {r.id: r for r in dataset.revisions}
        assert by_id[repo["A"]].branches == ("main", "feat")
        assert by_id[repo["B"]].branches == ("main",)
        assert by_id[repo["C"]].branches == ("feat",)

    def test_tags_attached_to_revisions(self, dataset, repo):
        by_id = {r.id: r for r in dataset.revisions}
        assert by_id[repo["A"]].tags == ("v1",)
        assert by_id[repo["B"]].tags == ()

    def test_default_branch_used_when_none_configured(self, results_dir, repo):
        # Only main (the checked-out branch) is configured, so C — which
        # sits on feat alone — is unattributable and skipped entirely.
        dataset = _load(results_dir, repo=str(repo["path"]))
        by_id = {r.id: r for r in dataset.revisions}
        assert by_id[repo["B"]].branches == ("main",)
        assert repo["C"] not in by_id


@pytest.fixture(scope="module")
def enriched_site(results_dir, repo, tmp_path_factory):
    dataset = _load(results_dir, repo=str(repo["path"]), branches=["main", "feat"])
    site = tmp_path_factory.mktemp("site") / "html"
    HtmlOutputGenerator().generate(dataset, site, {})
    return site


@pytest.fixture(scope="module")
def enriched_index(enriched_site):
    return json.loads((enriched_site / "index.json").read_text())


class TestEnrichedSite:
    def test_branch_axis_has_real_names(self, enriched_index):
        assert enriched_index["params"]["branch"] == ["feat", "main"]

    def test_tags_map_to_revision_numbers(self, enriched_index, repo):
        assert enriched_index["tags"] == {"v1": 0}
        assert enriched_index["revision_to_hash"]["0"] == repo["A"]

    def test_commit_on_two_branches_graphed_on_both(self, enriched_site):
        main_graphs = list(enriched_site.glob("graphs/branch-main/**/time_x.json"))
        feat_graphs = list(enriched_site.glob("graphs/branch-feat/**/time_x.json"))
        assert len(main_graphs) == 1 and len(feat_graphs) == 1
        main_data = json.loads(main_graphs[0].read_text())
        feat_data = json.loads(feat_graphs[0].read_text())
        # A (revision 0, value 1.0) sits on both branches.
        assert main_data == [[0, 1.0], [1, 2.0]]
        assert feat_data == [[0, 1.0], [2, 3.0]]

    def test_revision_dates_are_commit_dates(self, enriched_index, repo):
        date_a = int(_git(repo["path"], "log", "-1", "--format=%ct", repo["A"]))
        assert enriched_index["revision_to_date"]["0"] == date_a * 1000


class TestErrors:
    def test_missing_configured_repo_named(self, results_dir, tmp_path):
        missing = tmp_path / "no-repo"
        with pytest.raises(UlvError, match="no-repo"):
            _load(results_dir, repo=str(missing))

    def test_non_repo_directory_named(self, results_dir, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(UlvError, match="plain"):
            _load(results_dir, repo=str(plain))

    def test_unknown_branch_named(self, results_dir, repo):
        with pytest.raises(UlvError, match="no-such-branch"):
            _load(results_dir, repo=str(repo["path"]), branches=["no-such-branch"])

    def test_branches_without_repo_rejected(self, results_dir):
        with pytest.raises(UlvError, match="branches"):
            _load(results_dir, branches=["main"])

    def test_plain_subdirectory_of_a_repo_rejected(self, repo):
        # A subdirectory inside a repository must not silently adopt the
        # enclosing repository as the configured one.
        subdir = repo["path"] / "sub"
        subdir.mkdir(exist_ok=True)
        with pytest.raises(UlvError, match="sub"):
            _load_repo_probe(subdir)


def _load_repo_probe(path):
    from ulv.gitrepo import GitRepo

    return GitRepo(path)


def _make_results(root, entries):
    """A one-machine results tree with one result file per (commit, date,
    value) entry."""
    root.mkdir()
    (root / "benchmarks.json").write_text(
        json.dumps(
            {
                "time_x": {
                    "name": "time_x",
                    "param_names": [],
                    "params": [],
                    "type": "time",
                    "unit": "seconds",
                },
                "version": 2,
            }
        )
    )
    box = root / "box"
    box.mkdir()
    (box / "machine.json").write_text(
        json.dumps({"machine": "box", "os": "Linux", "version": 1})
    )
    for commit, date, value in entries:
        (box / f"{commit[:8]}-py3.json").write_text(
            json.dumps(_result_file(commit, date, value))
        )
    return root


class TestUnattributableCommits:
    """ASV parity: results that cannot be placed in the configured
    history are warned about and skipped, never fatal and never graphed
    under a phantom branch (publish.py:178-201)."""

    def test_rebased_away_commit_skipped_with_diagnostic(self, repo, tmp_path, capsys):
        stranger = "f" * 40
        results = _make_results(
            tmp_path / "results",
            [
                (repo["A"], RESULT_DATE_A, 1.0),
                (stranger, 1767000000000, 9.0),
            ],
        )
        out_dir = tmp_path / "site"
        rc = main(
            [
                "build",
                "-i",
                "asv",
                "--input-dir",
                str(results),
                "-o",
                str(out_dir),
                "--repo",
                str(repo["path"]),
                "--branches",
                "main",
            ]
        )
        assert rc == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert stranger not in index["revision_to_hash"].values()
        assert list(index["revision_to_hash"].values()) == [repo["A"]]
        assert stranger in capsys.readouterr().err

    def test_commit_on_unconfigured_branch_not_graphed(self, repo, tmp_path, capsys):
        results = _make_results(
            tmp_path / "results",
            [
                (repo["A"], RESULT_DATE_A, 1.0),
                (repo["B"], RESULT_DATE_B, 2.0),
                (repo["C"], RESULT_DATE_C, 3.0),
            ],
        )
        out_dir = tmp_path / "site"
        rc = main(
            [
                "build",
                "-i",
                "asv",
                "--input-dir",
                str(results),
                "-o",
                str(out_dir),
                "--repo",
                str(repo["path"]),
                "--branches",
                "main",
            ]
        )
        assert rc == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert index["params"]["branch"] == ["main"]
        assert repo["C"] not in index["revision_to_hash"].values()
        assert list(out_dir.glob("graphs/branch-feat/**/*.json")) == []
        assert repo["C"] in capsys.readouterr().err


class TestCli:
    def test_build_with_repo_flags(self, results_dir, repo, tmp_path):
        out_dir = tmp_path / "site"
        rc = main(
            [
                "build",
                "-i",
                "asv",
                "--input-dir",
                str(results_dir),
                "-o",
                str(out_dir),
                "--repo",
                str(repo["path"]),
                "--branches",
                "main,feat",
            ]
        )
        assert rc == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert index["tags"] == {"v1": 0}
        assert index["params"]["branch"] == ["feat", "main"]

    def test_same_invocation_without_repo_still_builds(self, results_dir, tmp_path):
        out_dir = tmp_path / "site"
        rc = main(
            [
                "build",
                "-i",
                "asv",
                "--input-dir",
                str(results_dir),
                "-o",
                str(out_dir),
            ]
        )
        assert rc == 0
        index = json.loads((out_dir / "index.json").read_text())
        assert index["tags"] == {}
        assert index["params"]["branch"] == [""]
