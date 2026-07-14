"""Session journal reading.

A session journal is a JSONL file: one JSON object per line, written by
whatever ran the coding session — an agent harness, a shell hook, or a
human taking structured notes. mergescribe extracts three things from it,
without interpretation: commands that were run (with exit codes), notes
and decisions, and files that were touched.

The reader is deliberately liberal in the keys it accepts (``command`` /
``cmd`` / ``run``, ``exit_code`` / ``exitCode`` / ``status``, …) because
every harness spells its events slightly differently. The canonical
format is documented in ``docs/journal-format.md``. Unrecognized lines
are counted and skipped by default; ``strict=True`` raises
:class:`~mergescribe.errors.JournalError` at the first bad line instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .errors import JournalError

__all__ = ["JournalEvent", "Journal", "parse_journal", "load_journal"]

_COMMAND_KEYS = ("command", "cmd", "run", "shell", "input")
_TEXT_KEYS = ("text", "message", "note", "content", "summary")
_EXIT_KEYS = ("exit_code", "exitCode", "exit", "returncode", "code", "status")
_FILE_KEYS = ("files", "paths", "file", "path")

_KIND_ALIASES = {
    "command": "command",
    "cmd": "command",
    "run": "command",
    "shell": "command",
    "bash": "command",
    "exec": "command",
    "tool": "command",
    "note": "note",
    "comment": "note",
    "observation": "note",
    "log": "note",
    "summary": "note",
    "decision": "decision",
    "choice": "decision",
    "edit": "edit",
    "write": "edit",
    "patch": "edit",
    "file_edit": "edit",
}

_STATUS_WORDS_OK = frozenset({"ok", "pass", "passed", "success", "succeeded", "done"})
_STATUS_WORDS_FAIL = frozenset({"fail", "failed", "error", "errored", "nonzero"})


@dataclass(frozen=True)
class JournalEvent:
    """One extracted journal event.

    ``kind`` is one of ``command``, ``note``, ``decision``, ``edit``.
    ``exit_code`` is only meaningful for commands and may be ``None`` when
    the journal did not record an outcome.
    """

    kind: str
    text: str
    exit_code: Optional[int] = None
    files: Tuple[str, ...] = field(default=())
    line: int = 0
    source: str = ""


@dataclass(frozen=True)
class Journal:
    """All events extracted from one or more journal files."""

    events: Tuple[JournalEvent, ...]
    skipped: int = 0
    sources: Tuple[str, ...] = field(default=())

    def commands(self) -> List[JournalEvent]:
        return [event for event in self.events if event.kind == "command"]

    def notes(self) -> List[JournalEvent]:
        return [event for event in self.events if event.kind in ("note", "decision")]


def _coerce_exit(value: Any) -> Optional[int]:
    """Best-effort exit-code coercion: ints, digit strings, status words."""
    if isinstance(value, bool):  # bool is an int subclass; True means "ok" here
        return 0 if value else 1
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token.lstrip("-").isdigit():
            return int(token)
        if token in _STATUS_WORDS_OK:
            return 0
        if token in _STATUS_WORDS_FAIL:
            return 1
    return None


def _coerce_files(value: Any) -> Tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _first_key(obj: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def _event_from_object(obj: Dict[str, Any], line: int, source: str) -> Optional[JournalEvent]:
    """Map a raw JSON object onto a JournalEvent, or None if unrecognizable."""
    declared = obj.get("type") or obj.get("kind") or obj.get("event") or ""
    kind = _KIND_ALIASES.get(str(declared).strip().lower(), "")

    command = _first_key(obj, _COMMAND_KEYS)
    text = _first_key(obj, _TEXT_KEYS)
    files = _coerce_files(_first_key(obj, _FILE_KEYS))

    exit_value = _first_key(obj, _EXIT_KEYS)
    exit_code = _coerce_exit(exit_value) if exit_value is not None else None

    if kind == "command" or (not kind and isinstance(command, str) and command.strip()):
        if not isinstance(command, str) or not command.strip():
            return None
        return JournalEvent(
            kind="command",
            text=command.strip(),
            exit_code=exit_code,
            files=files,
            line=line,
            source=source,
        )
    if kind in ("note", "decision"):
        body = text if isinstance(text, str) else None
        if not body or not body.strip():
            return None
        return JournalEvent(kind=kind, text=body.strip(), files=files, line=line, source=source)
    if kind == "edit" or (not kind and files):
        if not files:
            return None
        label = text.strip() if isinstance(text, str) and text.strip() else ""
        return JournalEvent(kind="edit", text=label, files=files, line=line, source=source)
    if not kind and isinstance(text, str) and text.strip():
        return JournalEvent(kind="note", text=text.strip(), line=line, source=source)
    return None


def parse_journal(text: str, source: str = "<journal>", strict: bool = False) -> Journal:
    """Parse JSONL journal text into a :class:`Journal`."""
    events: List[JournalEvent] = []
    skipped = 0
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):  # allow comment/blank lines
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            if strict:
                raise JournalError(f"invalid JSON: {exc.msg}", source=source, line=number)
            skipped += 1
            continue
        if not isinstance(obj, dict):
            if strict:
                raise JournalError("journal line is not a JSON object", source=source, line=number)
            skipped += 1
            continue
        event = _event_from_object(obj, number, source)
        if event is None:
            if strict:
                raise JournalError("unrecognized journal event", source=source, line=number)
            skipped += 1
            continue
        events.append(event)
    return Journal(events=tuple(events), skipped=skipped, sources=(source,))


def load_journal(paths: List[str], strict: bool = False) -> Journal:
    """Read and concatenate one or more journal files, in the order given."""
    all_events: List[JournalEvent] = []
    skipped = 0
    sources: List[str] = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            raise JournalError(f"cannot read journal: {exc}", source=path)
        journal = parse_journal(text, source=path, strict=strict)
        all_events.extend(journal.events)
        skipped += journal.skipped
        sources.append(path)
    return Journal(events=tuple(all_events), skipped=skipped, sources=tuple(sources))
