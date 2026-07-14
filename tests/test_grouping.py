"""Commit grouping for PR sections and changelog categories."""

from mergescribe.conventional import parse_commit
from mergescribe.grouping import changelog_category, changelog_entries, group_commits


def make(subject, body="", sha="a"):
    return parse_commit(sha * 40, "Dev", "2026-07-10T09:00:00+00:00", subject, body)


class TestGroupCommits:
    def test_sections_in_significance_order_empty_omitted(self):
        commits = [make("docs: d"), make("feat: f"), make("fix: g")]
        assert [key for key, _ in group_commits(commits)] == ["feat", "fix", "docs"]
        assert [key for key, _ in group_commits([make("feat: only")])] == ["feat"]
        assert group_commits([make("Update readme")])[0][0] == "other"

    def test_order_within_section_preserved(self):
        commits = [make("feat: first", sha="a"), make("feat: second", sha="b")]
        _, entries = group_commits(commits)[0]
        assert [commit.description for commit in entries] == ["first", "second"]


class TestChangelogCategory:
    def test_default_mapping(self):
        assert changelog_category(make("feat: x")) == "Added"
        assert changelog_category(make("fix: x")) == "Fixed"
        assert changelog_category(make("perf: x")) == "Changed"
        assert changelog_category(make("refactor: x")) == "Changed"

    def test_housekeeping_excluded_unless_all_flag(self):
        for subject in ("docs: x", "test: x", "chore: x", "ci: x", "style: x"):
            assert changelog_category(make(subject)) == "", subject
        assert changelog_category(make("docs: x"), include_all=True) == "Changed"

    def test_breaking_housekeeping_always_included(self):
        # A breaking change must never silently vanish from the changelog.
        assert changelog_category(make("chore!: drop old runtime support")) == "Changed"

    def test_security_markers_get_security_category(self):
        assert changelog_category(make("fix(security): patch header injection")) == "Security"
        assert changelog_category(make("fix: address CVE-2026-1234 in parser")) == "Security"


class TestChangelogEntries:
    def test_categories_in_keep_a_changelog_order(self):
        commits = [make("fix: f"), make("feat: g"), make("fix(security): h")]
        categories = [category for category, _ in changelog_entries(commits)]
        assert categories == ["Added", "Fixed", "Security"]

    def test_breaking_listed_first_and_housekeeping_empty(self):
        commits = [make("feat: normal", sha="a"), make("feat!: breaking", sha="b")]
        _, entries = changelog_entries(commits)[0]
        assert entries[0].breaking
        assert changelog_entries([make("docs: x"), make("chore: y")]) == []
