#!/usr/bin/env bash
# Smoke test for mergescribe: build the deterministic demo repository, then
# drive every CLI subcommand end-to-end and grep-assert on real output.
# Self-contained: pure stdlib + local git, no network, idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# Zero runtime dependencies: running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mergescribe-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"
echo "[smoke] git:    $(git --version)"

# 1. --version agrees with the package version.
version_out="$("$PYTHON" -m mergescribe --version)"
pkg_version="$("$PYTHON" -c 'import mergescribe; print(mergescribe.__version__)')"
[ "$version_out" = "mergescribe $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

# 2. Build the pinned-date demo repository.
bash "$ROOT/examples/build_demo_repo.sh" "$WORKDIR/repo" >/dev/null \
  || fail "build_demo_repo.sh exited non-zero"

# 3. commits: all three branch commits parsed with the right types.
commits_out="$("$PYTHON" -m mergescribe -C "$WORKDIR/repo" commits --base main --head feature)"
echo "$commits_out" | sed 's/^/[commits] /'
echo "$commits_out" | grep -q "3 commits in main..feature" || fail "commits count wrong"
echo "$commits_out" | grep -q "feat" || fail "commits missing feat"

# 4. pr: full Markdown body with title, verification table, and linked issues.
pr_out="$("$PYTHON" -m mergescribe -C "$WORKDIR/repo" pr \
  --base main --head feature --journal "$ROOT/examples/session-journal.jsonl")"
echo "$pr_out" | head -6 | sed 's/^/[pr] /'
echo "$pr_out" | grep -q "^# feat(api): add cursor pagination" || fail "pr title missing"
echo "$pr_out" | grep -q "## Verification" || fail "pr missing Verification section"
echo "$pr_out" | grep -q "| test | \`pytest -q\` | 2 | pass (exit 0) |" \
  || fail "pr verification table wrong"
echo "$pr_out" | grep -q "Closes #42, #57." || fail "pr missing linked issues"
echo "$pr_out" | grep -q "no LLM involved" || fail "pr missing generator footer"

# 5. Determinism: a second run is byte-identical.
pr_again="$("$PYTHON" -m mergescribe -C "$WORKDIR/repo" pr \
  --base main --head feature --journal "$ROOT/examples/session-journal.jsonl")"
[ "$pr_out" = "$pr_again" ] || fail "pr output not byte-identical across runs"
echo "[smoke] pr output byte-identical across runs"

# 6. pr --format json parses and has the right shape.
"$PYTHON" -m mergescribe -C "$WORKDIR/repo" pr \
  --base main --head feature --format json \
  | "$PYTHON" -c '
import json, sys
report = json.load(sys.stdin)
assert report["commit_count"] == 3, report["commit_count"]
assert report["closes"] == [42, 57], report["closes"]
' || fail "pr JSON output malformed"

# 7. changelog: dated section from commit dates (not the wall clock).
cl_out="$("$PYTHON" -m mergescribe -C "$WORKDIR/repo" changelog \
  --base main --head feature --release 0.2.0)"
echo "$cl_out" | sed 's/^/[changelog] /'
echo "$cl_out" | grep -q "## \[0.2.0\] - 2026-07-11" || fail "changelog heading/date wrong"
echo "$cl_out" | grep -q "### Added" || fail "changelog missing Added"
echo "$cl_out" | grep -q "### Fixed" || fail "changelog missing Fixed"

# 8. changelog --insert is idempotent: second run leaves the file untouched.
"$PYTHON" -m mergescribe -C "$WORKDIR/repo" changelog \
  --base main --head feature --release 0.2.0 --insert "$WORKDIR/CHANGELOG.md" 2>/dev/null
cp "$WORKDIR/CHANGELOG.md" "$WORKDIR/CHANGELOG.first"
"$PYTHON" -m mergescribe -C "$WORKDIR/repo" changelog \
  --base main --head feature --release 0.2.0 --insert "$WORKDIR/CHANGELOG.md" 2>/dev/null
cmp -s "$WORKDIR/CHANGELOG.md" "$WORKDIR/CHANGELOG.first" \
  || fail "changelog --insert is not idempotent"
echo "[smoke] changelog --insert idempotent"

# 9. journal: evidence extraction with last-result-wins dedup.
journal_out="$("$PYTHON" -m mergescribe journal "$ROOT/examples/session-journal.jsonl")"
echo "$journal_out" | sed 's/^/[journal] /'
echo "$journal_out" | grep -q "\[test\] pytest -q  x2  pass (exit 0)" \
  || fail "journal evidence dedup wrong"

# 10. Errors are clean: unknown ref exits 1 with a message, no traceback.
set +e
err_out="$("$PYTHON" -m mergescribe -C "$WORKDIR/repo" pr --base no-such-ref 2>&1)"
err_rc=$?
set -e
[ "$err_rc" -eq 1 ] || fail "unknown ref should exit 1, got $err_rc"
echo "$err_out" | grep -q "mergescribe: error:" || fail "unknown ref lacks clean error"
if echo "$err_out" | grep -q "Traceback"; then fail "unknown ref printed a traceback"; fi

echo "SMOKE OK"
