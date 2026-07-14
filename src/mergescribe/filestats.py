"""Categorizing and summarizing per-file diff stats.

Reviewers triage a PR by *shape* before content: how much of the diff is
source versus tests versus docs versus config. This module assigns each
changed path to exactly one area using ordered, purely lexical rules (no
repository introspection), then folds the numstat into an aggregate
:class:`DiffSummary`.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from .gitlog import FileChange

__all__ = ["DiffSummary", "AREA_ORDER", "categorize", "summarize"]

#: Render order for file areas.
AREA_ORDER = ("source", "tests", "docs", "scripts", "config", "other")

_TEST_DIRS = frozenset({"test", "tests", "__tests__", "spec", "specs", "testdata"})
_DOC_DIRS = frozenset({"doc", "docs"})
_SCRIPT_DIRS = frozenset({"script", "scripts", "bin", "tools", "hack"})
_DOC_EXTS = frozenset({".md", ".rst", ".adoc", ".txt"})
_CONFIG_EXTS = frozenset({".toml", ".yaml", ".yml", ".ini", ".cfg", ".json", ".lock", ".conf"})
_SOURCE_EXTS = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".swift",
        ".kt", ".java", ".c", ".h", ".cc", ".cpp", ".hpp", ".rb", ".php", ".cs",
        ".scala", ".ex", ".exs", ".zig", ".lua", ".sql", ".html", ".css", ".scss",
    }
)
_CONFIG_BASENAMES = frozenset(
    {
        "makefile", "dockerfile", "justfile", "rakefile", "gemfile",
        "go.mod", "go.sum", "package.json", "package-lock.json", "pyproject.toml",
        "cargo.toml", "cargo.lock", "tsconfig.json", "setup.py", "setup.cfg",
    }
)
_TEST_FILE_RE = re.compile(
    r"(?:^test_.+|.+_test\.[^.]+|.+\.(?:test|spec)\.[^.]+|^conftest\.py)$"
)


@dataclass(frozen=True)
class DiffSummary:
    """Aggregate view of a diff: totals plus per-area breakdown."""

    files: int
    added: int
    deleted: int
    binary: int
    by_area: Tuple[Tuple[str, Tuple[int, int, int]], ...] = field(default=())
    #: by_area value = (file count, lines added, lines deleted), in AREA_ORDER.
    top: Tuple[FileChange, ...] = field(default=())

    @property
    def empty(self) -> bool:
        return self.files == 0


def categorize(path: str) -> str:
    """Assign a path to one area. Rules are ordered; first match wins.

    Order matters: ``tests/config.yaml`` is *tests* (it exercises the code),
    while ``docs/examples/demo.py`` is *docs* (it documents it).
    """
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return "other"
    basename = parts[-1]
    lower_dirs = {part.lower() for part in parts[:-1]}
    _, ext = posixpath.splitext(basename.lower())

    if lower_dirs & _TEST_DIRS or _TEST_FILE_RE.match(basename.lower()):
        return "tests"
    if (parts[0].lower() in _DOC_DIRS) or ext in _DOC_EXTS or basename.lower() == "license":
        return "docs"
    if parts[0].lower() in _SCRIPT_DIRS or ext == ".sh":
        return "scripts"
    if basename.lower() in _CONFIG_BASENAMES or ext in _CONFIG_EXTS or (
        basename.startswith(".") and ext not in _SOURCE_EXTS
    ):
        return "config"
    if ext in _SOURCE_EXTS:
        return "source"
    return "other"


def summarize(changes: Iterable[FileChange], top_n: int = 5) -> DiffSummary:
    """Fold file changes into a :class:`DiffSummary`.

    ``top`` holds the ``top_n`` files by churn (added+deleted), ties broken
    by path so the output is stable across runs.
    """
    changes = list(changes)
    per_area: Dict[str, List[int]] = {}
    total_added = 0
    total_deleted = 0
    binary = 0
    for change in changes:
        area = categorize(change.path)
        bucket = per_area.setdefault(area, [0, 0, 0])
        bucket[0] += 1
        bucket[1] += change.added
        bucket[2] += change.deleted
        total_added += change.added
        total_deleted += change.deleted
        if change.binary:
            binary += 1

    by_area = tuple(
        (area, (per_area[area][0], per_area[area][1], per_area[area][2]))
        for area in AREA_ORDER
        if area in per_area
    )
    top = tuple(
        sorted(changes, key=lambda change: (-change.churn, change.path))[:top_n]
    )
    return DiffSummary(
        files=len(changes),
        added=total_added,
        deleted=total_deleted,
        binary=binary,
        by_area=by_area,
        top=top,
    )
