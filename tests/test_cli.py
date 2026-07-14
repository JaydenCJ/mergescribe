"""CLI integration: every subcommand driven in-process against a real repo."""

import json

import pytest

from mergescribe import __version__
from mergescribe.cli import main


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


JOURNAL_LINES = [
    '{"type": "command", "command": "pytest -q", "exit_code": 1}',
    '{"type": "note", "text": "first run failed: off-by-one in cursor decoding"}',
    '{"type": "command", "command": "pytest -q", "exit_code": 0}',
    '{"type": "command", "command": "ruff check src", "exit_code": 0}',
    '{"type": "decision", "text": "kept cursors opaque base64"}',
]


class TestVersionAndHelp:
    def test_version_flag_and_bare_invocation(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        assert capsys.readouterr().out.strip() == f"mergescribe {__version__}"
        # No subcommand → help text and exit code 2, not a stack trace.
        code, out, _ = run(capsys)
        assert code == 2
        assert "pr" in out and "changelog" in out


class TestPrCommand:
    def test_markdown_body_contains_all_sections(self, capsys, feature_repo, journal_path):
        journal = journal_path(JOURNAL_LINES)
        code, out, _ = run(
            capsys, "-C", str(feature_repo.path), "pr",
            "--base", "main", "--head", "feature", "--journal", journal,
        )
        assert code == 0
        for heading in ("## Summary", "## Changes", "## Verification",
                        "## Session notes", "## Diff at a glance", "## Linked issues"):
            assert heading in out, heading
        assert "| test | `pytest -q` | 2 | pass (exit 0) |" in out
        # --title-only prints just the suggested first line.
        code, out, _ = run(
            capsys, "-C", str(feature_repo.path), "pr",
            "--base", "main", "--head", "feature", "--title-only",
        )
        assert code == 0
        assert out == "feat(api): add cursor pagination to list endpoints (+2 more commits)\n"

    def test_json_format_is_valid_and_shaped(self, capsys, feature_repo, journal_path):
        journal = journal_path(JOURNAL_LINES)
        code, out, _ = run(
            capsys, "-C", str(feature_repo.path), "pr",
            "--base", "main", "--head", "feature", "--journal", journal, "--format", "json",
        )
        assert code == 0
        report = json.loads(out)
        assert report["commit_count"] == 3
        assert report["closes"] == [42, 57]
        assert report["journal"]["checks"][0]["category"] == "test"

    def test_output_is_byte_identical_across_runs(self, capsys, feature_repo, journal_path):
        # The headline promise: same inputs, same bytes.
        journal = journal_path(JOURNAL_LINES)
        argv = ["-C", str(feature_repo.path), "pr", "--base", "main",
                "--head", "feature", "--journal", journal]
        _, first, _ = run(capsys, *argv)
        _, second, _ = run(capsys, *argv)
        assert first == second

    def test_empty_range_and_strict_journal_fail_cleanly(self, capsys, feature_repo, journal_path):
        code, _, err = run(
            capsys, "-C", str(feature_repo.path), "pr", "--base", "main", "--head", "main"
        )
        assert code == 1
        assert "no commits" in err
        journal = journal_path(["{broken"])
        code, _, err = run(
            capsys, "-C", str(feature_repo.path), "pr",
            "--base", "main", "--head", "feature",
            "--journal", journal, "--strict-journal",
        )
        assert code == 1
        assert "invalid JSON" in err

    def test_out_writes_file(self, capsys, feature_repo, tmp_path):
        target = tmp_path / "pr.md"
        code, out, err = run(
            capsys, "-C", str(feature_repo.path), "pr",
            "--base", "main", "--head", "feature", "--out", str(target),
        )
        assert code == 0
        assert out == ""
        assert "## Summary" in target.read_text(encoding="utf-8")


class TestChangelogCommand:
    def test_section_printed_with_commit_or_explicit_date(self, capsys, feature_repo):
        code, out, _ = run(
            capsys, "-C", str(feature_repo.path), "changelog",
            "--base", "main", "--head", "feature", "--release", "0.2.0",
        )
        assert code == 0
        assert out.startswith("## [0.2.0] - 2026-07-1")  # newest commit date, not today
        assert "### Added" in out and "### Fixed" in out
        code, out, _ = run(
            capsys, "-C", str(feature_repo.path), "changelog",
            "--base", "main", "--head", "feature",
            "--release", "0.2.0", "--date", "2027-01-01",
        )
        assert code == 0
        assert "## [0.2.0] - 2027-01-01" in out

    def test_insert_is_idempotent(self, capsys, feature_repo, tmp_path):
        target = tmp_path / "CHANGELOG.md"
        argv = ["-C", str(feature_repo.path), "changelog", "--base", "main",
                "--head", "feature", "--release", "0.2.0", "--insert", str(target)]
        code, _, err = run(capsys, *argv)
        assert code == 0 and "updated" in err
        first = target.read_bytes()
        code, _, err = run(capsys, *argv)
        assert code == 0 and "already up to date" in err
        assert target.read_bytes() == first

    def test_missing_base_ref_reports_git_error(self, capsys, repo):
        code, _, err = run(
            capsys, "-C", str(repo.path), "changelog", "--base", "no-such-ref",
        )
        assert code == 1
        assert "mergescribe: error:" in err


class TestCommitsCommand:
    def test_table_and_json_output(self, capsys, feature_repo):
        code, out, _ = run(
            capsys, "-C", str(feature_repo.path), "commits",
            "--base", "main", "--head", "feature",
        )
        assert code == 0
        assert "feat" in out and "fix" in out and "docs" in out
        assert "3 commits in main..feature" in out
        code, out, _ = run(
            capsys, "-C", str(feature_repo.path), "commits",
            "--base", "main", "--head", "feature", "--format", "json",
        )
        payload = json.loads(out)
        assert [entry["type"] for entry in payload] == ["feat", "fix", "docs"]
        assert payload[0]["closes"] == [42]


class TestJournalCommand:
    def test_table_output(self, capsys, journal_path):
        journal = journal_path(JOURNAL_LINES)
        code, out, _ = run(capsys, "journal", journal)
        assert code == 0
        assert "events: 5" in out
        assert "[test] pytest -q  x2  pass (exit 0)" in out
        assert "decision: kept cursors opaque base64" in out

    def test_json_output_counts_skipped(self, capsys, journal_path):
        journal = journal_path(['{"telemetry": 1}'] + JOURNAL_LINES)
        code, out, _ = run(capsys, "journal", journal, "--format", "json")
        payload = json.loads(out)
        assert payload["skipped"] == 1
        assert payload["events"] == 5
        # A missing journal file is an operational error, not a stack trace.
        code, _, err = run(capsys, "journal", "/nonexistent/journal.jsonl")
        assert code == 1
        assert "cannot read journal" in err
