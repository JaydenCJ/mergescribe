"""Grouping commits into PR sections and changelog categories.

Two fixed, documented mappings live here:

* PR sections — every Conventional Commit type gets its own heading, in a
  significance order (features first, style last).
* Keep-a-Changelog categories — only user-visible types make the changelog
  by default (feat/fix/perf/refactor/revert plus anything breaking or
  security-flagged); housekeeping types are excluded unless asked for.

Both mappings are pure lookup tables: no scoring, no heuristics that could
drift between runs.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .conventional import Commit

__all__ = [
    "SECTION_ORDER",
    "SECTION_TITLES",
    "CATEGORY_ORDER",
    "group_commits",
    "changelog_entries",
]

#: PR "Changes" section order, most reader-relevant first.
SECTION_ORDER = (
    "feat", "fix", "perf", "refactor", "revert", "docs",
    "test", "build", "ci", "chore", "style", "other",
)

SECTION_TITLES: Dict[str, str] = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "refactor": "Refactoring",
    "revert": "Reverts",
    "docs": "Documentation",
    "test": "Tests",
    "build": "Build",
    "ci": "CI",
    "chore": "Chores",
    "style": "Style",
    "other": "Other changes",
}

#: Keep a Changelog category order.
CATEGORY_ORDER = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

#: Types included in the changelog by default, and where they land.
_CHANGELOG_MAP: Dict[str, str] = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "revert": "Changed",
}

_SECURITY_MARKERS = ("security", "cve-", "vulnerability")


def group_commits(commits: Iterable[Commit]) -> List[Tuple[str, List[Commit]]]:
    """Group commits by type, returning only non-empty sections in order."""
    buckets: Dict[str, List[Commit]] = {}
    for commit in commits:
        key = commit.type if commit.type in SECTION_ORDER else "other"
        buckets.setdefault(key, []).append(commit)
    return [(key, buckets[key]) for key in SECTION_ORDER if key in buckets]


def _is_security(commit: Commit) -> bool:
    """Security commits get their own changelog category, per Keep a Changelog."""
    haystack = f"{commit.scope} {commit.description}".lower()
    return any(marker in haystack for marker in _SECURITY_MARKERS)


def changelog_category(commit: Commit, include_all: bool = False) -> str:
    """Changelog category for a commit, or "" if it should be excluded.

    Breaking commits are always included (a reader must not miss them),
    landing in Changed unless their base type already maps elsewhere.
    """
    if _is_security(commit):
        return "Security"
    mapped = _CHANGELOG_MAP.get(commit.type, "")
    if mapped:
        return mapped
    if commit.breaking:
        return "Changed"
    if include_all:
        return "Changed"
    return ""


def changelog_entries(
    commits: Iterable[Commit], include_all: bool = False
) -> List[Tuple[str, List[Commit]]]:
    """Commits per changelog category, only non-empty, in CATEGORY_ORDER.

    Within a category, breaking commits are listed first (readers scan the
    top of each section), then original commit order.
    """
    buckets: Dict[str, List[Commit]] = {}
    for commit in commits:
        category = changelog_category(commit, include_all=include_all)
        if category:
            buckets.setdefault(category, []).append(commit)
    for entries in buckets.values():
        entries.sort(key=lambda commit: 0 if commit.breaking else 1)
    return [(category, buckets[category]) for category in CATEGORY_ORDER if category in buckets]
