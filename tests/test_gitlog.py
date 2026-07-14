"""git log/diff parsing: pure parsers plus real-repository integration."""

import pytest

from mergescribe.errors import GitError
from mergescribe.gitlog import parse_log, parse_numstat, read_commits, read_numstat

FS = "\x1f"


def record(sha, author, date, subject, body=""):
    return FS.join([sha, author, date, subject, body]) + "\0"


class TestParseLog:
    def test_records_parse_including_multiline_bodies(self):
        text = record("a" * 40, "Dev Example", "2026-07-10T09:00:00+00:00", "feat: x")
        commits = parse_log(text)
        assert len(commits) == 1
        assert commits[0].type == "feat"
        assert commits[0].author == "Dev Example"
        # NUL-separated records mean multi-line bodies cannot break parsing.
        body = "line one\n\nCloses: #5"
        multi = record("b" * 40, "Dev", "2026-07-10T09:00:00+00:00", "fix: y", body)
        assert parse_log(multi)[0].closes == (5,)

    def test_empty_input_and_malformed_record(self):
        assert parse_log("") == []
        with pytest.raises(GitError):
            parse_log("only-two\x1ffields\0")


class TestParseNumstat:
    def test_basic_lines_and_churn(self):
        changes = parse_numstat("10\t2\tsrc/app.py\n0\t5\tREADME.md\n")
        assert [(change.path, change.added, change.deleted) for change in changes] == [
            ("src/app.py", 10, 2),
            ("README.md", 0, 5),
        ]
        assert changes[0].churn == 12

    def test_binary_files_flagged_with_zero_counts(self):
        changes = parse_numstat("-\t-\tdocs/assets/logo.png\n")
        assert changes[0].binary
        assert changes[0].added == 0 and changes[0].deleted == 0

    def test_renames_resolve_to_new_path(self):
        assert parse_numstat("3\t1\tsrc/{old => new}/mod.py\n")[0].path == "src/new/mod.py"
        assert parse_numstat("0\t0\told_name.py => new_name.py\n")[0].path == "new_name.py"


class TestRealRepository:
    def test_read_commits_returns_branch_commits_oldest_first(self, feature_repo):
        commits = read_commits("main", "feature", repo=str(feature_repo.path))
        assert [commit.type for commit in commits] == ["feat", "fix", "docs"]
        assert commits[0].date.startswith("2026-07-10T")
        # ...and never leaks history that is already on the base branch.
        assert all("scaffold" not in commit.subject for commit in commits)

    def test_read_commits_empty_range(self, repo):
        assert read_commits("main", "main", repo=str(repo.path)) == []

    def test_read_numstat_reports_changed_files(self, feature_repo):
        changes = read_numstat("main", "feature", repo=str(feature_repo.path))
        paths = {change.path for change in changes}
        assert "src/pagination.py" in paths
        assert "tests/test_pagination.py" in paths

    def test_unknown_ref_raises_git_error_with_stderr(self, repo):
        with pytest.raises(GitError) as excinfo:
            read_commits("no-such-ref", "main", repo=str(repo.path))
        assert "no-such-ref" in str(excinfo.value)
