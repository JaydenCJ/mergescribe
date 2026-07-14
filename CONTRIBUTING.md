# Contributing to mergescribe

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Development setup

```bash
git clone https://github.com/JaydenCJ/mergescribe
cd mergescribe
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                 # 91 offline tests (pure parsers + real-repo CLI runs)
bash scripts/smoke.sh  # end-to-end: demo repo, every subcommand, must print SMOKE OK
```

Both must pass before a pull request is reviewed. The suite runs fully
offline: the only external tool it touches is your local `git` binary.

## Ground rules

- **No new runtime dependencies.** The package is standard-library only;
  that is a feature. Test-only dependencies belong in the `dev` extra.
- **Determinism is the contract.** Nothing in the extraction or rendering
  path may read the wall clock, the network, environment locale, or any
  other input that could make two runs differ. If a change can break
  byte-identical output, it needs a test proving it does not.
- **Classification tables over heuristics.** New command runners, commit
  types, or path categories are added to the static tables in
  `evidence.py`, `grouping.py`, and `filestats.py` — with a test per entry.
- **Every public API needs an English docstring and a test.** Keep logic in
  pure, unit-testable modules; only `gitlog.run_git` may spawn a process.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` are line-for-line parallel; update all three when you
  change one (English is the authoritative version).

## Reporting bugs

Please include `mergescribe --version`, the exact command line, the commit
subjects in the range (`mergescribe commits --base …`), and — if a journal
is involved — the journal lines that were misread. All of these are local
text; nothing sensitive leaves your machine unless you paste it.

## Security

Please do not open public issues for suspected vulnerabilities; use
GitHub's private vulnerability reporting on this repository instead.
