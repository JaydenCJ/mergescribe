"""Path categorization and diff summarization."""

from mergescribe.filestats import categorize, summarize
from mergescribe.gitlog import FileChange


class TestCategorize:
    def test_source_files(self):
        for path in ("src/app.py", "lib/parser.rs", "cmd/main.go", "web/app.tsx"):
            assert categorize(path) == "source", path

    def test_test_files_by_directory_and_name(self):
        for path in ("tests/test_app.py", "spec/user_spec.rb", "pkg/testdata/case1.json",
                     "src/parser_test.go", "src/app.test.ts", "conftest.py"):
            assert categorize(path) == "tests", path

    def test_tests_beat_docs_and_config(self):
        # Order matters: fixtures under tests/ are tests, not config.
        assert categorize("tests/fixtures/config.yaml") == "tests"
        assert categorize("tests/README.md") == "tests"

    def test_docs_and_scripts(self):
        for path in ("README.md", "docs/design.md", "docs/examples/demo.py", "LICENSE"):
            assert categorize(path) == "docs", path
        for path in ("scripts/smoke.sh", "bin/release", "deploy.sh"):
            assert categorize(path) == "scripts", path

    def test_config_including_dotfiles(self):
        for path in ("pyproject.toml", "package-lock.json", ".gitignore",
                     "Makefile", "config/settings.ini", ".eslintrc.json"):
            assert categorize(path) == "config", path

    def test_unknown_extension_is_other_and_separators_normalized(self):
        assert categorize("assets/logo.png") == "other"
        assert categorize("tests\\test_win.py") == "tests"
        assert categorize("./src/app.py") == "source"


class TestSummarize:
    def changes(self):
        return [
            FileChange("src/app.py", 100, 20),
            FileChange("src/util.py", 10, 5),
            FileChange("tests/test_app.py", 40, 0),
            FileChange("README.md", 8, 2),
            FileChange("assets/logo.png", 0, 0, binary=True),
        ]

    def test_totals_binary_count_and_empty_diff(self):
        summary = summarize(self.changes())
        assert (summary.files, summary.added, summary.deleted) == (5, 158, 27)
        assert summary.binary == 1
        assert summarize([]).empty
        assert summarize([]).by_area == ()

    def test_area_breakdown_in_fixed_order(self):
        summary = summarize(self.changes())
        assert [area for area, _ in summary.by_area] == ["source", "tests", "docs", "other"]
        by_area = dict(summary.by_area)
        assert by_area["source"] == (2, 110, 25)
        assert by_area["tests"] == (1, 40, 0)

    def test_top_files_by_churn_ties_broken_by_path(self):
        changes = [FileChange("b.py", 5, 5), FileChange("a.py", 5, 5), FileChange("c.py", 100, 0)]
        summary = summarize(changes, top_n=2)
        assert [change.path for change in summary.top] == ["c.py", "a.py"]
