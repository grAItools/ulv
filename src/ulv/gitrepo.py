"""Minimal git CLI wrapper for optional enrichment (spec Decision 4).

Shells out to `git` the way asv does (asv/plugins/git.py) — no
gitpython. Enrichment only runs when a repository is explicitly
configured, and a configured-but-unusable repository is an error, never
a silent downgrade. Semantics mirror asv: topological revision order is
`rev-list --all --date-order --reverse`, branch membership follows
first-parent history, and annotated tags resolve to their commit.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ulv.errors import UlvError


class GitRepo:
    """Read-only access to one git repository."""

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_dir():
            raise UlvError(
                f"configured git repository not found: {self.path}",
                offending_input=str(self.path),
            )
        self._git("rev-parse", "--git-dir")

    def _git(self, *args: str) -> str:
        env = dict(
            os.environ,
            GIT_TERMINAL_PROMPT="0",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
        )
        try:
            completed = subprocess.run(
                ["git", "-C", str(self.path), *args],
                env=env,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise UlvError(
                f"cannot run git for repository {self.path}: {exc}",
                offending_input=str(self.path),
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"git exited {completed.returncode}"
            raise UlvError(
                f"git {' '.join(args[:1])} failed for repository {self.path}: {detail}",
                offending_input=str(self.path),
            )
        return completed.stdout

    def default_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").strip()

    def rev_order(self) -> list[str]:
        """All commits, oldest first, in asv's revision-numbering order
        (git.py:197-211)."""
        return self._git("rev-list", "--all", "--date-order", "--reverse").split()

    def commit_date_ms(self, commit: str) -> int:
        """Committer date as a JS millisecond timestamp."""
        return int(self._git("log", "-1", "--format=%ct", commit).strip()) * 1000

    def tags(self) -> dict[str, str]:
        """tag name -> commit hash, annotated tags resolved (git.py:185-189)."""
        result = {}
        for tag in self._git("tag", "-l", "--sort=taggerdate").splitlines():
            if tag:
                result[tag] = self._git("rev-list", "-n", "1", tag).strip()
        return result

    def branch_commits(self, branch: str) -> list[str]:
        """Commits on a branch, first-parent history only (git.py:194-195)."""
        return self._git("rev-list", "--first-parent", branch, "--").split()
