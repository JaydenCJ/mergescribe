"""Conventional Commits parsing: headers, footers, breaking flags, issues."""

from mergescribe.conventional import parse_commit, parse_footers


def make(subject, body=""):
    return parse_commit("a" * 40, "Dev Example", "2026-07-10T09:00:00+00:00", subject, body)


class TestHeader:
    def test_plain_and_scoped_headers(self):
        plain = make("feat: add pagination")
        assert (plain.type, plain.scope, plain.description) == ("feat", "", "add pagination")
        assert not plain.breaking
        assert plain.short_sha == "a" * 7
        scoped = make("fix(api): return 404 for missing cursor")
        assert (scoped.type, scoped.scope) == ("fix", "api")
        assert scoped.description == "return 404 for missing cursor"
        bang = make("feat(api)!: remove the v1 endpoints")
        assert bang.breaking
        assert bang.description == "remove the v1 endpoints"

    def test_unknown_type_degrades_to_other(self):
        # Hand-written histories are common; nothing may be rejected.
        commit = make("Update readme with screenshots")
        assert commit.type == "other"
        assert commit.description == "Update readme with screenshots"
        assert not commit.conventional
        # "wip:" looks conventional but is not a known type; keep it verbatim.
        assert make("wip: half-finished parser").type == "other"

    def test_type_case_insensitive_but_space_required(self):
        assert make("Fix: handle empty input").type == "fix"
        # Missing space after the colon means "not a conventional header".
        assert make("feat:no space").type == "other"


class TestFooters:
    def test_footer_block_extracted(self):
        footers, body = parse_footers("Some explanation.\n\nReviewed-by: Alice\nCloses: #12")
        assert footers == (("Reviewed-by", "Alice"), ("Closes", "#12"))
        assert body == "Some explanation."

    def test_prose_paragraph_with_colon_is_not_footers(self):
        # "Note: this matters" inside prose must not eat the paragraph.
        text = "First line.\n\nNote: this matters, but the next line is prose\nso this is not a footer block"
        footers, body = parse_footers(text)
        assert footers == ()
        assert body == text

    def test_continuation_lines_and_empty_body(self):
        footers, _ = parse_footers("BREAKING CHANGE: the config file\n  moved to a new location")
        assert footers == (("BREAKING CHANGE", "the config file moved to a new location"),)
        assert parse_footers("") == ((), "")

    def test_breaking_change_footer_both_spellings(self):
        commit = make("refactor: rework config loading", "BREAKING CHANGE: keys are now nested")
        assert commit.breaking
        assert commit.breaking_notes == ("keys are now nested",)
        assert make("feat: new engine", "BREAKING-CHANGE: old flags removed").breaking


class TestIssues:
    def test_issue_refs_collected_without_closing(self):
        # A plain "#N" mention is a reference, never an implicit close.
        commit = make("fix: workaround for #12", "See also #34 and #12 again")
        assert commit.issues == (12, 34)
        assert commit.closes == ()

    def test_closes_footer_marks_issue_closed(self):
        commit = make("fix: crash on empty input", "Closes: #99")
        assert commit.closes == (99,)
        assert 99 in commit.issues

    def test_inline_fixes_phrase_and_multi_issue_footers(self):
        assert make("fix: null cursor", "This fixes #57 for good.").closes == (57,)
        assert make("fix: batch", "Fixes: #1, #2, #3").closes == (1, 2, 3)
