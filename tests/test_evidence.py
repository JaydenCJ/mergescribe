"""Command classification and evidence folding: the verification table's brain."""

from mergescribe.evidence import classify_command, collect_checks, normalize_command
from mergescribe.journal import JournalEvent


def command(text, exit_code=0):
    return JournalEvent(kind="command", text=text, exit_code=exit_code)


class TestClassify:
    def test_common_test_runners(self):
        for text in ("pytest -q", "python -m pytest tests/", "go test ./...",
                     "cargo test", "npm test", "node --test", "tox -e py311",
                     "bash scripts/smoke.sh", "./scripts/smoke.sh"):
            assert classify_command(text) == "test", text

    def test_typecheckers_and_linters(self):
        for text in ("mypy src", "pyright", "tsc --noEmit"):
            assert classify_command(text) == "typecheck", text
        for text in ("ruff check src", "eslint .", "cargo clippy -- -D warnings", "go vet ./..."):
            assert classify_command(text) == "lint", text

    def test_longest_prefix_wins(self):
        # "ruff format" must beat the bare "ruff" lint rule; same for make.
        assert classify_command("ruff format src tests") == "format"
        assert classify_command("ruff check src") == "lint"
        assert classify_command("make test") == "test"
        assert classify_command("make") == "build"

    def test_non_check_commands_return_none(self):
        for text in ("git status", "ls -la", "cd src", "cat README.md", "grep -r foo ."):
            assert classify_command(text) is None, text

    def test_env_prefixes_stripped_and_normalized_to_one_key(self):
        assert classify_command("CI=1 pytest -q") == "test"
        assert classify_command("env FOO=bar time cargo test") == "test"
        # Dedup depends on this: re-runs with env tweaks are the same check.
        assert normalize_command("pytest   -q") == "pytest -q"
        assert normalize_command("CI=1 time pytest -q") == normalize_command("pytest  -q")


class TestCollect:
    def test_last_exit_code_wins(self):
        # A failing run later fixed must report as passing — the final state ships.
        checks = collect_checks([command("pytest -q", 1), command("pytest -q", 0)])
        assert len(checks) == 1
        assert checks[0].exit_code == 0
        assert checks[0].runs == 2

    def test_final_failure_and_unknown_outcomes_are_honest(self):
        failed = collect_checks([command("pytest -q", 0), command("pytest -q", 2)])[0]
        assert failed.outcome == "FAIL (exit 2)"
        assert failed.passed is False
        unknown = collect_checks([command("pytest -q", None)])[0]
        assert unknown.outcome == "no result recorded"
        assert unknown.passed is None

    def test_category_ordering(self):
        # test < typecheck < lint < format < build, regardless of journal order.
        checks = collect_checks(
            [command("make"), command("ruff check ."), command("mypy src"), command("pytest")]
        )
        assert [check.category for check in checks] == ["test", "typecheck", "lint", "build"]

    def test_irrelevant_events_excluded(self):
        note = JournalEvent(kind="note", text="pytest is great")
        checks = collect_checks([note, command("git push"), command("pytest")])
        assert len(checks) == 1
        assert checks[0].command == "pytest"

    def test_distinct_commands_stay_distinct_and_output_is_deterministic(self):
        checks = collect_checks([command("pytest tests/a.py"), command("pytest tests/b.py")])
        assert len(checks) == 2
        events = [command("mypy src", 0), command("pytest", 1), command("pytest", 0)]
        assert collect_checks(events) == collect_checks(events)
