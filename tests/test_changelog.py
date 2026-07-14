"""Changelog rendering and idempotent merging into an existing file."""

from mergescribe.changelog import default_date, merge_into, render_section
from mergescribe.conventional import parse_commit


def make(subject, body="", date="2026-07-10T09:00:00+00:00", sha="a"):
    return parse_commit(sha * 40, "Dev", date, subject, body)


class TestRenderSection:
    def test_versioned_heading_with_date_unreleased_without(self):
        dated = render_section([make("feat: x")], version="0.2.0", date="2026-07-11")
        assert dated.startswith("## [0.2.0] - 2026-07-11")
        unreleased = render_section([make("feat: x")], version="Unreleased", date="2026-07-11")
        assert unreleased.startswith("## [Unreleased]\n")

    def test_categories_rendered_with_bullets(self):
        section = render_section(
            [make("feat(api): add pagination", "Closes: #42"), make("fix: null cursor")]
        )
        assert "### Added" in section
        assert "- **api:** Add pagination (#42)" in section
        assert "### Fixed" in section
        breaking = render_section([make("feat!: drop v1 endpoints")])
        assert "- **Breaking:** Drop v1 endpoints" in breaking

    def test_housekeeping_only_range_says_so_unless_all(self):
        housekeeping = [make("docs: rewrite install guide"), make("chore: y")]
        assert "_No user-facing changes in this range._" in render_section(housekeeping)
        assert "### Changed" in render_section(housekeeping, include_all=True)


class TestDefaultDate:
    def test_newest_commit_date_wins_regardless_of_order(self):
        commits = [
            make("feat: newer", date="2026-07-12T08:00:00+00:00"),
            make("fix: older", date="2026-07-10T08:00:00+00:00"),
        ]
        assert default_date(commits) == "2026-07-12"
        assert default_date([]) == ""


EXISTING = """# Changelog

Header prose.

## [0.1.0] - 2026-07-01

### Added

- First release
"""


class TestMergeInto:
    def section(self, version="0.2.0"):
        return render_section([make("feat: add pagination")], version=version, date="2026-07-11")

    def test_new_version_inserted_above_previous_release(self):
        merged = merge_into(EXISTING, self.section(), "0.2.0")
        assert merged.index("## [0.2.0]") < merged.index("## [0.1.0]")
        assert "Header prose." in merged

    def test_same_version_replaced_not_duplicated(self):
        once = merge_into(EXISTING, self.section(), "0.2.0")
        twice = merge_into(once, self.section(), "0.2.0")
        assert twice == once
        assert twice.count("## [0.2.0]") == 1

    def test_replacement_updates_content(self):
        once = merge_into(EXISTING, self.section(), "0.2.0")
        updated_section = render_section(
            [make("feat: add pagination"), make("fix: y")], version="0.2.0", date="2026-07-11"
        )
        merged = merge_into(once, updated_section, "0.2.0")
        assert "### Fixed" in merged
        assert merged.count("## [0.2.0]") == 1

    def test_changelog_without_sections_appends_and_stays_stable(self):
        # An absent file gets the standard Keep-a-Changelog header first.
        created = merge_into("", self.section(), "0.2.0")
        assert created.startswith("# Changelog")
        assert "Keep a Changelog" in created
        # Replacing the final section must not accrete trailing newlines.
        base = "# Changelog\n\nNothing yet.\n"
        once = merge_into(base, self.section(), "0.2.0")
        assert "Nothing yet." in once
        assert once.rstrip().endswith("- Add pagination")
        twice = merge_into(once, self.section(), "0.2.0")
        assert twice == once

    def test_version_match_is_case_insensitive(self):
        once = merge_into(EXISTING, self.section("Unreleased"), "Unreleased")
        twice = merge_into(once, self.section("unreleased"), "unreleased")
        assert twice.count("nreleased]") == 1
