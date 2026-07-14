"""Session journal parsing: key aliases, coercion, strictness, multi-file."""

import pytest

from mergescribe.errors import JournalError
from mergescribe.journal import load_journal, parse_journal


class TestEventShapes:
    def test_canonical_and_aliased_command_events(self):
        journal = parse_journal(
            '{"type": "command", "command": "pytest -q", "exit_code": 0}\n'
            '{"cmd": "go test ./...", "exitCode": 1}'  # bare {"cmd": ...} still counts
        )
        first, second = journal.events
        assert (first.kind, first.text, first.exit_code) == ("command", "pytest -q", 0)
        assert (second.kind, second.exit_code) == ("command", 1)

    def test_status_values_coerce_to_exit_codes(self):
        cases = [
            ('{"type": "run", "command": "mypy src", "status": "passed"}', 0),
            ('{"type": "shell", "command": "npm test", "status": "failed"}', 1),
            ('{"command": "cargo test", "exit_code": "2"}', 2),
            ('{"command": "pytest", "status": true}', 0),
        ]
        for line, expected in cases:
            assert parse_journal(line).events[0].exit_code == expected, line

    def test_command_without_outcome_has_none_exit(self):
        journal = parse_journal('{"type": "command", "command": "pytest"}')
        assert journal.events[0].exit_code is None

    def test_note_decision_and_bare_text_events(self):
        journal = parse_journal(
            '{"type": "note", "text": "cache was stale"}\n'
            '{"type": "decision", "message": "kept the old wire format"}'
        )
        assert [event.kind for event in journal.events] == ["note", "decision"]
        assert journal.events[1].text == "kept the old wire format"
        assert parse_journal('{"text": "observed flaky retry"}').events[0].kind == "note"

    def test_edit_events_collect_files(self):
        journal = parse_journal(
            '{"type": "edit", "files": ["src/a.py", "src/b.py"]}\n'
            '{"path": "src/c.py"}'  # a bare path key is recognizably an edit
        )
        assert journal.events[0].files == ("src/a.py", "src/b.py")
        assert journal.events[1].kind == "edit"


class TestRobustness:
    def test_blank_and_comment_lines_ignored(self):
        journal = parse_journal('\n# session started\n{"command": "pytest"}\n\n')
        assert len(journal.events) == 1
        assert journal.skipped == 0
        assert journal.events[0].line == 3  # events keep their source line number

    def test_malformed_lines_skipped_and_counted(self):
        journal = parse_journal(
            'not json at all\n'      # invalid JSON
            '[1, 2, 3]\n'            # not an object
            '{"telemetry": 42}\n'    # object with no recognizable event
            '{"command": "pytest"}'
        )
        assert len(journal.events) == 1
        assert journal.skipped == 3

    def test_strict_mode_raises_with_location(self):
        with pytest.raises(JournalError) as excinfo:
            parse_journal('{"command": "pytest"}\n{broken', source="session.jsonl", strict=True)
        assert excinfo.value.line == 2
        assert "session.jsonl" in str(excinfo.value)


class TestLoadJournal:
    def test_multiple_files_concatenate_and_missing_file_errors(self, journal_path):
        first = journal_path(['{"command": "pytest", "exit_code": 0}'], name="a.jsonl")
        second = journal_path(['{"type": "note", "text": "done"}'], name="b.jsonl")
        journal = load_journal([first, second])
        assert [event.kind for event in journal.events] == ["command", "note"]
        assert journal.sources == (first, second)
        with pytest.raises(JournalError):
            load_journal(["/nonexistent/journal.jsonl"])

    def test_commands_and_notes_accessors(self, journal_path):
        path = journal_path(
            [
                '{"command": "pytest", "exit_code": 0}',
                '{"type": "decision", "text": "kept v1 schema"}',
                '{"type": "edit", "files": ["a.py"]}',
            ]
        )
        journal = load_journal([path])
        assert len(journal.commands()) == 1
        assert len(journal.notes()) == 1
