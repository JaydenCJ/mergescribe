"""mergescribe — deterministic PR descriptions and changelogs.

Builds pull-request bodies and Keep-a-Changelog sections from two local
sources of truth — git history and session journals — with no LLM in the
loop: the same inputs always produce byte-identical output.

Public API re-exported here; the CLI lives in :mod:`mergescribe.cli`.
"""

from .changelog import default_date, merge_into, render_section
from .conventional import Commit, parse_commit
from .errors import GitError, JournalError, MergescribeError
from .evidence import Check, classify_command, collect_checks
from .filestats import DiffSummary, categorize, summarize
from .gitlog import FileChange, parse_log, parse_numstat, read_commits, read_numstat
from .grouping import changelog_entries, group_commits
from .journal import Journal, JournalEvent, load_journal, parse_journal
from .prbody import build_report, render_markdown, suggest_title

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Commit",
    "Check",
    "DiffSummary",
    "FileChange",
    "Journal",
    "JournalEvent",
    "MergescribeError",
    "GitError",
    "JournalError",
    "parse_commit",
    "parse_log",
    "parse_numstat",
    "read_commits",
    "read_numstat",
    "parse_journal",
    "load_journal",
    "classify_command",
    "collect_checks",
    "categorize",
    "summarize",
    "group_commits",
    "changelog_entries",
    "build_report",
    "render_markdown",
    "suggest_title",
    "render_section",
    "merge_into",
    "default_date",
]
