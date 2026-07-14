"""The ``mergescribe`` command-line interface.

Subcommands:

* ``pr``        — build a PR description (Markdown or JSON) for base..head
* ``changelog`` — build a Keep-a-Changelog section; optionally splice it
                  into an existing CHANGELOG.md, idempotently
* ``commits``   — show how each commit in the range was parsed (debug view)
* ``journal``   — show what was extracted from session journals (debug view)

All subcommands are deterministic: same repository state + same journals
in → byte-identical text out. Nothing here touches the network or the
wall clock (the changelog date comes from the commits or ``--date``).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .changelog import default_date, merge_into, render_section
from .errors import MergescribeError
from .evidence import collect_checks
from .filestats import summarize
from .gitlog import read_commits, read_numstat
from .journal import Journal, load_journal
from .prbody import build_report, render_markdown

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mergescribe",
        description=(
            "Build PR descriptions and changelogs deterministically from "
            "session journals and git history — no LLM."
        ),
    )
    parser.add_argument("--version", action="version", version=f"mergescribe {__version__}")
    parser.add_argument(
        "-C", "--repo", default=None, metavar="DIR", help="run as if started in DIR"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    pr = sub.add_parser("pr", help="build a PR description for BASE..HEAD")
    _add_range_args(pr)
    pr.add_argument(
        "--journal", action="append", default=[], metavar="FILE",
        help="session journal (JSONL); repeatable",
    )
    pr.add_argument(
        "--format", choices=("markdown", "json"), default="markdown",
        help="output format (default: markdown)",
    )
    pr.add_argument("--title-only", action="store_true", help="print only the suggested title")
    pr.add_argument(
        "--max-summary", type=int, default=8, metavar="N",
        help="max bullets in the Summary section (default: 8)",
    )
    pr.add_argument("--out", default=None, metavar="FILE", help="write to FILE instead of stdout")
    pr.add_argument(
        "--strict-journal", action="store_true",
        help="fail on the first malformed journal line instead of skipping",
    )

    changelog = sub.add_parser("changelog", help="build a changelog section for BASE..HEAD")
    _add_range_args(changelog)
    changelog.add_argument(
        "--release", default="Unreleased", metavar="VERSION",
        help='version heading (default: "Unreleased")',
    )
    changelog.add_argument(
        "--date", default=None, metavar="YYYY-MM-DD",
        help="release date (default: date of the newest commit in the range)",
    )
    changelog.add_argument(
        "--all", action="store_true",
        help="include housekeeping commit types (docs/test/chore/…) under Changed",
    )
    changelog.add_argument(
        "--insert", default=None, metavar="FILE",
        help="splice the section into FILE in place (idempotent) instead of printing",
    )

    commits = sub.add_parser("commits", help="show parsed commits for BASE..HEAD")
    _add_range_args(commits)
    commits.add_argument(
        "--format", choices=("table", "json"), default="table",
        help="output format (default: table)",
    )

    journal = sub.add_parser("journal", help="show checks and notes extracted from journals")
    journal.add_argument("paths", nargs="+", metavar="FILE", help="journal files (JSONL)")
    journal.add_argument(
        "--format", choices=("table", "json"), default="table",
        help="output format (default: table)",
    )
    journal.add_argument(
        "--strict", action="store_true",
        help="fail on the first malformed line instead of skipping",
    )
    return parser


def _add_range_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base", required=True, metavar="REF", help="base ref (e.g. main)")
    parser.add_argument("--head", default="HEAD", metavar="REF", help="head ref (default: HEAD)")


def _cmd_pr(args: argparse.Namespace) -> int:
    commits = read_commits(args.base, args.head, repo=args.repo)
    if not commits:
        print(f"mergescribe: no commits in {args.base}..{args.head}", file=sys.stderr)
        return 1
    diff = summarize(read_numstat(args.base, args.head, repo=args.repo))
    journal: Optional[Journal] = None
    checks = None
    if args.journal:
        journal = load_journal(args.journal, strict=args.strict_journal)
        checks = collect_checks(journal.events)
    report = build_report(
        commits, diff=diff, checks=checks, journal=journal,
        base=args.base, head=args.head,
    )
    if args.title_only:
        output = str(report["title"]) + "\n"
    elif args.format == "json":
        output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    else:
        title = str(report["title"])
        body = render_markdown(report, version=__version__, max_summary=args.max_summary)
        output = f"# {title}\n\n{body}"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


def _cmd_changelog(args: argparse.Namespace) -> int:
    commits = read_commits(args.base, args.head, repo=args.repo)
    if not commits:
        print(f"mergescribe: no commits in {args.base}..{args.head}", file=sys.stderr)
        return 1
    date = args.date if args.date is not None else default_date(commits)
    section = render_section(
        commits, version=args.release, date=date, include_all=args.all
    )
    if args.insert:
        try:
            with open(args.insert, "r", encoding="utf-8") as handle:
                existing = handle.read()
        except FileNotFoundError:
            existing = ""
        merged = merge_into(existing, section, args.release)
        if merged != existing:
            with open(args.insert, "w", encoding="utf-8") as handle:
                handle.write(merged)
            print(f"updated {args.insert} ([{args.release}])", file=sys.stderr)
        else:
            print(f"{args.insert} already up to date ([{args.release}])", file=sys.stderr)
    else:
        sys.stdout.write(section)
    return 0


def _cmd_commits(args: argparse.Namespace) -> int:
    commits = read_commits(args.base, args.head, repo=args.repo)
    if args.format == "json":
        payload = [
            {
                "sha": commit.sha,
                "type": commit.type,
                "scope": commit.scope,
                "breaking": commit.breaking,
                "description": commit.description,
                "issues": list(commit.issues),
                "closes": list(commit.closes),
            }
            for commit in commits
        ]
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    if not commits:
        print(f"no commits in {args.base}..{args.head}")
        return 0
    for commit in commits:
        marker = "!" if commit.breaking else " "
        scope = f"({commit.scope})" if commit.scope else ""
        print(f"{commit.short_sha}  {commit.type:<8}{marker} {scope:<12} {commit.description}")
    print(f"{len(commits)} commit{'s' if len(commits) != 1 else ''} in {args.base}..{args.head}")
    return 0


def _cmd_journal(args: argparse.Namespace) -> int:
    journal = load_journal(args.paths, strict=args.strict)
    checks = collect_checks(journal.events)
    if args.format == "json":
        payload = {
            "sources": list(journal.sources),
            "events": len(journal.events),
            "skipped": journal.skipped,
            "checks": [
                {
                    "category": check.category,
                    "command": check.command,
                    "runs": check.runs,
                    "exit_code": check.exit_code,
                }
                for check in checks
            ],
            "notes": [
                {"kind": event.kind, "text": event.text} for event in journal.notes()
            ],
        }
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    print(f"events: {len(journal.events)}  skipped: {journal.skipped}")
    if checks:
        print("checks:")
        for check in checks:
            print(f"  [{check.category}] {check.command}  x{check.runs}  {check.outcome}")
    else:
        print("checks: none recognized")
    notes = journal.notes()
    if notes:
        print("notes:")
        for event in notes:
            prefix = "decision: " if event.kind == "decision" else ""
            print(f"  - {prefix}{event.text}")
    return 0


_HANDLERS = {
    "pr": _cmd_pr,
    "changelog": _cmd_changelog,
    "commits": _cmd_commits,
    "journal": _cmd_journal,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        return _HANDLERS[args.command](args)
    except MergescribeError as exc:
        print(f"mergescribe: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
