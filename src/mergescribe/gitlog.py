"""Reading commit ranges and diffs out of a local git repository.

All parsing is pure (``parse_log`` / ``parse_numstat`` take strings), so the
whole module is unit-testable without a repository; only :func:`run_git`
shells out, and only to the local ``git`` binary — never the network.

The log format uses ASCII unit separators (0x1f) between fields and NUL
(``-z``) between records, so subjects and bodies containing newlines, tabs,
or quotes round-trip losslessly.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .conventional import Commit, parse_commit
from .errors import GitError

__all__ = [
    "FileChange",
    "run_git",
    "parse_log",
    "parse_numstat",
    "read_commits",
    "read_numstat",
]

_FIELD_SEP = "\x1f"
_LOG_FORMAT = "%H%x1f%an%x1f%cI%x1f%s%x1f%b"
_FIELD_COUNT = 5


@dataclass(frozen=True)
class FileChange:
    """One file's diff stats. ``binary`` files report zero line counts."""

    path: str
    added: int
    deleted: int
    binary: bool = False

    @property
    def churn(self) -> int:
        return self.added + self.deleted


def run_git(args: Sequence[str], repo: Optional[str] = None) -> str:
    """Run ``git <args>`` and return stdout, raising :class:`GitError` on failure."""
    command = ["git"]
    if repo:
        command += ["-C", repo]
    command += list(args)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise GitError("git executable not found on PATH", command=" ".join(command))
    if result.returncode != 0:
        raise GitError(
            f"git {' '.join(args[:2])} failed (exit {result.returncode})",
            command=" ".join(command),
            stderr=result.stderr,
        )
    return result.stdout


def parse_log(text: str) -> List[Commit]:
    """Parse ``git log -z --format=<H|an|cI|s|b>`` output into commits."""
    commits: List[Commit] = []
    for record in text.split("\0"):
        if not record.strip():
            continue
        fields = record.split(_FIELD_SEP)
        if len(fields) != _FIELD_COUNT:
            raise GitError(
                f"unexpected log record with {len(fields)} fields (want {_FIELD_COUNT})"
            )
        sha, author, date, subject, body = fields
        commits.append(parse_commit(sha.strip(), author, date, subject, body))
    return commits


def parse_numstat(text: str) -> List[FileChange]:
    """Parse ``git diff --numstat`` output.

    Binary files show ``-`` for both counts; renames appear as
    ``old => new`` or ``dir/{old => new}/file`` — we keep the *new* path,
    because that is the path reviewers will see in the tree.
    """
    changes: List[FileChange] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue  # tolerate stray non-numstat lines
        raw_added, raw_deleted, path = parts[0], parts[1], "\t".join(parts[2:])
        binary = raw_added == "-" or raw_deleted == "-"
        added = 0 if binary else int(raw_added)
        deleted = 0 if binary else int(raw_deleted)
        changes.append(FileChange(path=_resolve_rename(path), added=added, deleted=deleted, binary=binary))
    return changes


def _resolve_rename(path: str) -> str:
    """Reduce a git rename path to the post-rename path."""
    if "{" in path and " => " in path and "}" in path:
        # e.g. "src/{old => new}/mod.py" -> "src/new/mod.py"
        prefix, rest = path.split("{", 1)
        inner, suffix = rest.split("}", 1)
        _, new = inner.split(" => ", 1)
        joined = prefix + new + suffix
        return joined.replace("//", "/")
    if " => " in path:
        return path.split(" => ", 1)[1]
    return path


def read_commits(base: str, head: str = "HEAD", repo: Optional[str] = None) -> List[Commit]:
    """Commits reachable from ``head`` but not ``base``, oldest first.

    Merge commits are skipped: on a PR branch they are almost always
    "merge main into branch" noise, and their real content is already
    present as regular commits.
    """
    out = run_git(
        ["log", "--reverse", "--no-merges", "-z", f"--format={_LOG_FORMAT}", f"{base}..{head}"],
        repo=repo,
    )
    return parse_log(out)


def read_numstat(base: str, head: str = "HEAD", repo: Optional[str] = None) -> List[FileChange]:
    """Per-file diff stats for ``base...head`` (merge-base comparison).

    The three-dot form matches how code review platforms compute a PR diff:
    changes on the branch since it diverged, ignoring drift on ``base``.
    """
    out = run_git(["diff", "--numstat", f"{base}...{head}"], repo=repo)
    return parse_numstat(out)
