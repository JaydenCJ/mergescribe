"""Conventional Commits parsing.

Turns a raw commit (sha, author, date, subject, body) into a structured
:class:`Commit`: type, scope, breaking flag, description, footers, breaking
notes, and referenced/closed issue numbers. Parsing follows the Conventional
Commits 1.0.0 spec closely, but never rejects a commit — a subject that does
not match the ``type(scope): description`` header is classified as type
``"other"`` and kept verbatim, so hand-written histories still produce
useful reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

__all__ = ["Commit", "KNOWN_TYPES", "parse_commit", "parse_footers"]

#: Commit types recognized as Conventional Commits headers. Anything else in
#: the type position (e.g. "Update readme") is treated as a plain subject.
KNOWN_TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)

_HEADER_RE = re.compile(
    r"^(?P<type>[A-Za-z]+)"
    r"(?:\((?P<scope>[^()]*)\))?"
    r"(?P<bang>!)?"
    r":\s+(?P<desc>\S.*)$"
)

# A footer key is a hyphenated word token ("Reviewed-by") or the two literal
# BREAKING spellings; the separator is ": " or " #" (per the spec).
_FOOTER_RE = re.compile(
    r"^(?P<key>BREAKING CHANGE|BREAKING-CHANGE|[A-Za-z][A-Za-z0-9-]*)"
    r"(?::[ \t]+|[ \t]+(?=#))(?P<value>.*)$"
)

_ISSUE_RE = re.compile(r"#(\d+)\b")
_CLOSING_INLINE_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.IGNORECASE
)

#: Footer keys whose issue references mean "this PR closes that issue".
_CLOSING_KEYS = frozenset(
    {"closes", "close", "closed", "fixes", "fix", "fixed", "resolves", "resolve", "resolved"}
)


@dataclass(frozen=True)
class Commit:
    """One parsed commit. ``type`` is ``"other"`` for non-conventional subjects."""

    sha: str
    author: str
    date: str  # committer date, strict ISO 8601 (git %cI)
    subject: str
    type: str
    scope: str
    breaking: bool
    description: str
    body: str
    footers: Tuple[Tuple[str, str], ...] = field(default=())
    breaking_notes: Tuple[str, ...] = field(default=())
    issues: Tuple[int, ...] = field(default=())
    closes: Tuple[int, ...] = field(default=())

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @property
    def conventional(self) -> bool:
        return self.type != "other"


def parse_footers(body: str) -> Tuple[Tuple[Tuple[str, str], ...], str]:
    """Split ``body`` into (footers, remaining body).

    The footer block is the last blank-line-separated paragraph, and only
    counts if every line in it is a ``Key: value`` footer or an indented
    continuation of the previous footer. Otherwise the body is returned
    unchanged with no footers — a trailing prose paragraph that merely
    *contains* a colon is not a footer block.
    """
    stripped = body.rstrip()
    if not stripped:
        return (), ""
    paragraphs = re.split(r"\n[ \t]*\n", stripped)
    last = paragraphs[-1]
    footers: List[Tuple[str, str]] = []
    for line in last.splitlines():
        if not line.strip():
            continue
        match = _FOOTER_RE.match(line)
        if match:
            footers.append((match.group("key"), match.group("value").strip()))
        elif footers and line[:1] in (" ", "\t"):
            # Continuation line: fold into the previous footer's value.
            key, value = footers[-1]
            footers[-1] = (key, (value + " " + line.strip()).strip())
        else:
            return (), stripped  # not a clean footer block
    if not footers:
        return (), stripped
    remaining = "\n\n".join(paragraphs[:-1]).rstrip()
    return tuple(footers), remaining


def _is_breaking_key(key: str) -> bool:
    return key.upper() in ("BREAKING CHANGE", "BREAKING-CHANGE")


def _collect_issues(*texts: str) -> Tuple[int, ...]:
    """All distinct ``#N`` references, in first-mention order."""
    seen: List[int] = []
    for text in texts:
        for match in _ISSUE_RE.finditer(text):
            number = int(match.group(1))
            if number not in seen:
                seen.append(number)
    return tuple(seen)


def _collect_closes(
    footers: Tuple[Tuple[str, str], ...], *texts: str
) -> Tuple[int, ...]:
    """Issue numbers this commit claims to close.

    Sources: footers with a closing key ("Closes: #12") and inline closing
    phrases in prose ("fixes #34"). Order is first mention; duplicates folded.
    """
    seen: List[int] = []

    def add(number: int) -> None:
        if number not in seen:
            seen.append(number)

    for key, value in footers:
        if key.lower() in _CLOSING_KEYS:
            for match in _ISSUE_RE.finditer(value):
                add(int(match.group(1)))
    for text in texts:
        for match in _CLOSING_INLINE_RE.finditer(text):
            add(int(match.group(1)))
    return tuple(seen)


def parse_commit(sha: str, author: str, date: str, subject: str, body: str = "") -> Commit:
    """Parse one commit into a :class:`Commit`.

    Never raises: a malformed header degrades to type ``"other"`` with the
    whole subject as the description, so downstream grouping always has
    something honest to show.
    """
    subject = subject.strip()
    footers, remaining_body = parse_footers(body)

    ctype = "other"
    scope = ""
    breaking = False
    description = subject

    match = _HEADER_RE.match(subject)
    if match and match.group("type").lower() in KNOWN_TYPES:
        ctype = match.group("type").lower()
        scope = (match.group("scope") or "").strip()
        breaking = match.group("bang") == "!"
        description = match.group("desc").strip()

    breaking_notes = tuple(
        value for key, value in footers if _is_breaking_key(key) and value
    )
    if breaking_notes:
        breaking = True

    issues = _collect_issues(subject, body)
    closes = _collect_closes(footers, subject, remaining_body)

    return Commit(
        sha=sha,
        author=author,
        date=date,
        subject=subject,
        type=ctype,
        scope=scope,
        breaking=breaking,
        description=description,
        body=remaining_body,
        footers=footers,
        breaking_notes=breaking_notes,
        issues=issues,
        closes=closes,
    )
