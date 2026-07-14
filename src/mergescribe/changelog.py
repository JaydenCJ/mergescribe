"""Rendering Keep-a-Changelog sections and merging them into CHANGELOG.md.

`render_section` produces one ``## [version] - date`` block from grouped
commits. `merge_into` splices that block into an existing changelog:

* if a section for the same version already exists it is **replaced**, so
  regenerating is idempotent — running the command twice yields the same
  file byte for byte;
* otherwise the new section is inserted above the previous newest release.

The release date is never taken from the wall clock: it comes from an
explicit ``--date`` or from the newest commit in the range, so the same
inputs always produce the same file.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from .conventional import Commit
from .grouping import changelog_entries

__all__ = ["render_section", "merge_into", "default_date"]

_SECTION_HEAD_RE = re.compile(r"^## \[(?P<version>[^\]]+)\]", re.MULTILINE)

_DEFAULT_HEADER = """# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
"""


def default_date(commits: Sequence[Commit]) -> str:
    """Release date = the date of the newest commit in the range (not today).

    Commits arrive oldest-first from gitlog, but we take the max of the ISO
    dates rather than trusting order, so reordered input cannot change the
    result.
    """
    dates = [commit.date[:10] for commit in commits if commit.date]
    return max(dates) if dates else ""


def _entry_line(commit: Commit) -> str:
    scope = f"**{commit.scope}:** " if commit.scope else ""
    breaking = "**Breaking:** " if commit.breaking else ""
    description = commit.description[:1].upper() + commit.description[1:]
    issue = f" (#{commit.closes[0]})" if commit.closes else ""
    return f"- {breaking}{scope}{description}{issue}"


def render_section(
    commits: Sequence[Commit],
    version: str = "Unreleased",
    date: str = "",
    include_all: bool = False,
) -> str:
    """Render one changelog section (heading + categorized bullets)."""
    heading = f"## [{version}]"
    if date and version.lower() != "unreleased":
        heading += f" - {date}"
    lines: List[str] = [heading, ""]
    entries = changelog_entries(commits, include_all=include_all)
    if not entries:
        lines.append("_No user-facing changes in this range._")
        lines.append("")
        return "\n".join(lines)
    for category, category_commits in entries:
        lines.append(f"### {category}")
        lines.append("")
        for commit in category_commits:
            lines.append(_entry_line(commit))
        lines.append("")
    return "\n".join(lines)


def _find_section_span(text: str, version: str) -> Optional[Tuple[int, int]]:
    """Character span of the existing ``## [version]`` section, if any."""
    for match in _SECTION_HEAD_RE.finditer(text):
        if match.group("version").lower() == version.lower():
            next_match = _SECTION_HEAD_RE.search(text, match.end())
            end = next_match.start() if next_match else len(text)
            return (match.start(), end)
    return None


def merge_into(existing: str, section: str, version: str) -> str:
    """Splice ``section`` into an existing changelog text, idempotently.

    Same-version section → replaced in place. New version → inserted before
    the first existing ``## [`` heading. Empty/absent changelog → a standard
    Keep-a-Changelog header is created first.
    """
    section = section.rstrip() + "\n"
    if not existing.strip():
        return _DEFAULT_HEADER + "\n" + section

    span = _find_section_span(existing, version)
    if span is not None:
        start, end = span
        rest = existing[end:].lstrip("\n")
        return existing[:start] + section + ("\n" + rest if rest else "")

    first = _SECTION_HEAD_RE.search(existing)
    if first is not None:
        insert_at = first.start()
        return existing[:insert_at] + section + "\n" + existing[insert_at:]

    return existing.rstrip() + "\n\n" + section
