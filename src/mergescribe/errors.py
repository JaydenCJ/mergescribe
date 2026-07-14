"""Exception hierarchy for mergescribe.

Everything raised on purpose derives from :class:`MergescribeError`, so the
CLI can catch one type, print a clean message, and exit 1 — stack traces are
reserved for genuine bugs.
"""

from __future__ import annotations

__all__ = ["MergescribeError", "GitError", "JournalError"]


class MergescribeError(Exception):
    """Base class for all errors deliberately raised by mergescribe."""


class GitError(MergescribeError):
    """A git invocation failed or produced unparseable output."""

    def __init__(self, message: str, *, command: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        base = super().__str__()
        if self.stderr:
            return f"{base}: {self.stderr.strip()}"
        return base


class JournalError(MergescribeError):
    """A session journal is malformed (only raised in strict mode)."""

    def __init__(self, message: str, *, source: str = "", line: int = 0) -> None:
        super().__init__(message)
        self.source = source
        self.line = line

    def __str__(self) -> str:
        base = super().__str__()
        if self.source:
            return f"{self.source}:{self.line}: {base}"
        return base
