# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Conventional Commits parser that never rejects a commit: full header
  parsing (type, scope, `!`), footer blocks with continuation lines,
  `BREAKING CHANGE`/`BREAKING-CHANGE` notes, and issue extraction that
  distinguishes closing references (`Fixes #57`, `Closes: #42`) from plain
  mentions; non-conventional subjects degrade to a verbatim "other" entry.
- Lossless git range reader using NUL/unit-separator log records, plus a
  numstat parser handling binary files and both git rename notations.
- JSONL session-journal reader with liberal key aliases (`command`/`cmd`,
  `exit_code`/`status`, …), exit-code coercion from status words, and a
  strict mode that reports the file and line of the first malformed entry.
- Verification-evidence extraction: a static token-prefix table classifies
  journal commands into test/typecheck/lint/format/build, dedupes re-runs
  by normalized command, and keeps the last exit code — the state that
  actually ships.
- PR body generator: deterministic title suggestion, summary bullets,
  per-type change sections with short SHAs, breaking-change section,
  verification table (or an explicit "no journal provided" statement),
  session notes, diff-by-area table, and linked issues — as Markdown or JSON.
- Changelog generator mapping commit types onto Keep-a-Changelog categories
  (breaking and security commits always included), with release dates taken
  from commit history, never the wall clock, and idempotent `--insert`
  splicing into an existing CHANGELOG.md.
- `mergescribe` CLI: `pr`, `changelog`, `commits`, `journal` subcommands,
  `--format json` everywhere it makes sense, clean exit codes (0/1/2).
- Deterministic demo repository builder and sample journal in `examples/`,
  journal format specification in `docs/journal-format.md`.
- 91 offline pytest tests and `scripts/smoke.sh` driving every subcommand
  end-to-end against a pinned-date repository.

### Notes

- The repository ships no CI workflow; verification is local —
  `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/mergescribe/releases/tag/v0.1.0
