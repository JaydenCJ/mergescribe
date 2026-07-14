# mergescribe examples

Everything here is offline and deterministic — the demo repository uses
pinned commit dates and identity, so the output below is byte-identical on
every machine.

## Files

| File | Purpose |
|---|---|
| `build_demo_repo.sh` | Creates a demo git repo (`main` + a 3-commit `feature` branch) with pinned dates |
| `session-journal.jsonl` | A session journal matching that branch: a failing test run, a fix, green checks, one decision |

## Walkthrough

From the repository root (no install needed — the package has zero runtime
dependencies):

```bash
export PYTHONPATH=src
bash examples/build_demo_repo.sh /tmp/mergescribe-demo

# The PR body, assembled from commits + journal:
python3 -m mergescribe -C /tmp/mergescribe-demo pr \
  --base main --head feature \
  --journal examples/session-journal.jsonl

# The changelog section for the same range:
python3 -m mergescribe -C /tmp/mergescribe-demo changelog \
  --base main --head feature --release 0.2.0

# Debug views: how commits were parsed, what the journal contained.
python3 -m mergescribe -C /tmp/mergescribe-demo commits --base main --head feature
python3 -m mergescribe journal examples/session-journal.jsonl
```

Run any command twice — the output is identical, because there is nothing
in the pipeline that could answer differently the second time.

The journal format (event kinds, accepted key aliases, exit-code coercion)
is documented in [`docs/journal-format.md`](../docs/journal-format.md).
