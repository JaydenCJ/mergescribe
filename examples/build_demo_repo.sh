#!/usr/bin/env bash
# Build a small, fully deterministic demo repository for mergescribe.
#
# Usage: bash examples/build_demo_repo.sh <target-dir>
#
# The repo gets a `main` branch with one scaffold commit and a `feature`
# branch with three Conventional Commits (feat/fix/docs). Author identity
# and commit dates are pinned, so the generated PR body and changelog are
# byte-identical on every machine, every time.
set -euo pipefail

TARGET="${1:?usage: build_demo_repo.sh <target-dir>}"
mkdir -p "$TARGET"

export GIT_AUTHOR_NAME="Dev Example" GIT_AUTHOR_EMAIL="dev@example.test"
export GIT_COMMITTER_NAME="Dev Example" GIT_COMMITTER_EMAIL="dev@example.test"

stamp() {
  export GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1"
}

git -C "$TARGET" init -q -b main .

stamp "2026-07-10T09:00:00+00:00"
printf 'print("hello")\n' > "$TARGET/app.py"
git -C "$TARGET" add -A
git -C "$TARGET" commit -qm "chore: initial scaffold"

git -C "$TARGET" checkout -qb feature

stamp "2026-07-11T10:00:00+00:00"
mkdir -p "$TARGET/src" "$TARGET/tests"
printf 'def paginate(cursor=None):\n    return {"items": [], "next": cursor}\n' > "$TARGET/src/pagination.py"
printf 'def test_paginate():\n    pass\n' > "$TARGET/tests/test_pagination.py"
git -C "$TARGET" add -A
git -C "$TARGET" commit -qm "feat(api): add cursor pagination to list endpoints" -m "Closes #42"

stamp "2026-07-11T11:00:00+00:00"
printf 'def paginate(cursor=None):\n    if cursor is None:\n        return {"items": []}\n    return {"items": [], "next": cursor}\n' > "$TARGET/src/pagination.py"
git -C "$TARGET" add -A
git -C "$TARGET" commit -qm "fix(api): return 404 instead of 500 for missing cursor" -m "Fixes #57"

stamp "2026-07-11T12:00:00+00:00"
printf '# demo\n\nPagination is documented here.\n' > "$TARGET/README.md"
git -C "$TARGET" add -A
git -C "$TARGET" commit -qm "docs: document pagination query parameters"

echo "demo repo ready at $TARGET (branches: main, feature)"
