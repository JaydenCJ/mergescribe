# Session journal format

A session journal is a **JSONL** file: one JSON object per line. Blank lines
and lines starting with `#` are ignored. mergescribe reads journals written
by agent harnesses, shell hooks, or humans — anything that can append one
JSON object per event.

mergescribe extracts exactly three things and interprets nothing:

1. **Commands** that were run, with exit codes → the *Verification* table
2. **Notes and decisions** → the *Session notes* list
3. **Files touched** → reserved for cross-checking against the diff (roadmap)

## Event kinds

The event kind comes from the `type`, `kind`, or `event` key. Accepted
values and their aliases:

| Kind | Aliases | Required payload |
|---|---|---|
| `command` | `cmd`, `run`, `shell`, `bash`, `exec`, `tool` | a command string |
| `note` | `comment`, `observation`, `log`, `summary` | a text string |
| `decision` | `choice` | a text string |
| `edit` | `write`, `patch`, `file_edit` | one or more file paths |

An object with **no** `type` key is still recognized when its payload is
unambiguous: a `command`/`cmd` key makes it a command, a `files`/`path` key
makes it an edit, a bare `text` key makes it a note.

## Key aliases

| Field | Accepted keys |
|---|---|
| command string | `command`, `cmd`, `run`, `shell`, `input` |
| text | `text`, `message`, `note`, `content`, `summary` |
| exit code | `exit_code`, `exitCode`, `exit`, `returncode`, `code`, `status` |
| files | `files`, `paths`, `file`, `path` |

## Exit-code coercion

Exit codes may be integers, digit strings, booleans, or status words:

| Journal value | Coerced to |
|---|---|
| `0`, `"0"`, `true`, `"ok"`, `"pass"`, `"passed"`, `"success"`, `"succeeded"`, `"done"` | `0` |
| `false`, `"fail"`, `"failed"`, `"error"`, `"errored"`, `"nonzero"` | `1` |
| `2`, `"2"`, … | the number |
| anything else / absent | `null` — reported as "no result recorded" |

## Example

```jsonl
{"type": "command", "command": "pytest -q", "exit_code": 1}
{"type": "note", "text": "first run failed: off-by-one in cursor decoding"}
{"type": "edit", "files": ["src/pagination.py"]}
{"type": "command", "command": "pytest -q", "exit_code": 0}
{"type": "decision", "text": "kept cursors opaque base64 instead of numeric offsets"}
```

Reading this journal, `mergescribe pr` reports `pytest -q` as one check,
run twice, final result **pass (exit 0)** — the last run of a command is
the state the PR actually ships with, while the note preserves the failure
story for the reviewer.

## Strictness

By default, unrecognized or malformed lines are skipped and counted (the
count is visible in `mergescribe journal --format json` and in the PR
report's `journal.skipped` field). Pass `--strict-journal` (or
`strict=True` in the API) to fail on the first bad line with its file and
line number instead.
