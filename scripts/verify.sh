#!/usr/bin/env bash
# verify.sh — single verification gate, invoked by humans and by the Stop hook.
#
# Exit code is what matters:
#   0  - everything green
#   2  - explicit failure (the Stop hook treats this as "do not stop yet")
#   ≠0 - some other failure
#
# Keep this fast (<60s ideally). Slow gates belong in CI, not in the agent loop.

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Before the Python project is bootstrapped there is nothing to lint or test.
if [ ! -f pyproject.toml ]; then
  printf "verify: skipped — no pyproject.toml yet (project not bootstrapped).\n"
  exit 0
fi

failed=0
run() {
  local label="$1"; shift
  printf "\n=== %s ===\n" "$label"
  if "$@"; then
    printf "✓ %s\n" "$label"
  else
    printf "✗ %s (exit %d)\n" "$label" "$?"
    failed=1
  fi
}

run "lint" uv run ruff check .
run "test" uv run pytest -q
run "docs" uv run python scripts/check_docs_staleness.py
run "docs-build" uv run zensical build

if [ "$failed" -ne 0 ]; then
  printf "\nverify: one or more checks failed.\n"
  exit 2
fi

printf "\nverify: all checks passed.\n"
