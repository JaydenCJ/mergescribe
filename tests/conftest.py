"""Shared fixtures: deterministic temp git repositories and journal helpers.

Git repos are built with pinned author/committer identity and dates, so
commit hashes and log output are stable within a test run and no test
depends on the wall clock. Everything is offline: only the local ``git``
binary is invoked.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import pytest

FIXED_ENV = {
    "GIT_AUTHOR_NAME": "Dev Example",
    "GIT_AUTHOR_EMAIL": "dev@example.test",
    "GIT_COMMITTER_NAME": "Dev Example",
    "GIT_COMMITTER_EMAIL": "dev@example.test",
}


class RepoBuilder:
    """Tiny helper for building deterministic git histories in tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self._tick = 0
        self.git("init", "-q", "-b", "main", ".")

    def git(self, *args: str) -> str:
        env = dict(os.environ)
        env.update(FIXED_ENV)
        # Advance a fake clock one hour per commit for stable ordering.
        stamp = f"2026-07-10T{9 + self._tick:02d}:00:00+00:00"
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
        result = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return result.stdout

    def commit(self, subject: str, body: str = "", files: Optional[Dict[str, str]] = None) -> None:
        files = files or {f"file_{self._tick}.py": f"# change {self._tick}\n"}
        for name, content in files.items():
            target = self.path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        self.git("add", "-A")
        args: List[str] = ["commit", "-q", "-m", subject]
        if body:
            args += ["-m", body]
        self.git(*args)
        self._tick += 1

    def branch(self, name: str) -> None:
        self.git("checkout", "-q", "-b", name)


@pytest.fixture
def repo(tmp_path: Path) -> RepoBuilder:
    """An empty repo on branch ``main`` with one scaffold commit."""
    builder = RepoBuilder(tmp_path / "repo")
    builder.commit("chore: initial scaffold", files={"app.py": "print('hi')\n"})
    return builder


@pytest.fixture
def feature_repo(repo: RepoBuilder) -> RepoBuilder:
    """A repo with a three-commit feature branch on top of main."""
    repo.branch("feature")
    repo.commit(
        "feat(api): add cursor pagination to list endpoints",
        body="Closes #42",
        files={
            "src/pagination.py": "def paginate():\n    return []\n",
            "tests/test_pagination.py": "def test_paginate():\n    pass\n",
        },
    )
    repo.commit(
        "fix(api): return 404 instead of 500 for missing cursor",
        body="Fixes #57",
        files={"src/pagination.py": "def paginate():\n    return None\n"},
    )
    repo.commit(
        "docs: document pagination query parameters",
        files={"README.md": "# demo\n\npagination docs\n"},
    )
    return repo


@pytest.fixture
def journal_path(tmp_path: Path):
    """Write JSONL lines to a journal file and return its path."""

    def write(lines: List[str], name: str = "journal.jsonl") -> str:
        target = tmp_path / name
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(target)

    return write
