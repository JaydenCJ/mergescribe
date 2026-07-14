"""Turning journal command events into verification evidence.

A journal typically records dozens of shell commands; reviewers only care
about the ones that *verify* the change: tests, type checks, linters,
formatters, builds. This module classifies commands into those categories
by their leading tokens, deduplicates repeated invocations, and keeps the
**last** exit code per distinct command — the final state of the session
is what the PR ships with.

Classification is a static token-prefix table, not a model: the same
journal always yields the same table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .journal import JournalEvent

__all__ = ["Check", "CATEGORY_ORDER", "classify_command", "collect_checks"]

#: Render/report order for check categories.
CATEGORY_ORDER = ("test", "typecheck", "lint", "format", "build")

_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")

# Ordered rules: (category, token prefix). Longest matching prefix wins, so
# ("format", ("ruff", "format")) beats ("lint", ("ruff",)) for `ruff format`.
_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    # tests
    ("test", ("pytest",)),
    ("test", ("python", "-m", "pytest")),
    ("test", ("python3", "-m", "pytest")),
    ("test", ("python", "-m", "unittest")),
    ("test", ("python3", "-m", "unittest")),
    ("test", ("go", "test")),
    ("test", ("cargo", "test")),
    ("test", ("npm", "test")),
    ("test", ("npm", "run", "test")),
    ("test", ("yarn", "test")),
    ("test", ("pnpm", "test")),
    ("test", ("npx", "vitest")),
    ("test", ("npx", "jest")),
    ("test", ("vitest",)),
    ("test", ("jest",)),
    ("test", ("node", "--test")),
    ("test", ("deno", "test")),
    ("test", ("bun", "test")),
    ("test", ("tox",)),
    ("test", ("make", "test")),
    ("test", ("make", "check")),
    ("test", ("ctest",)),
    ("test", ("rspec",)),
    ("test", ("bundle", "exec", "rspec")),
    ("test", ("dotnet", "test")),
    ("test", ("mvn", "test")),
    ("test", ("gradle", "test")),
    ("test", ("./gradlew", "test")),
    ("test", ("swift", "test")),
    ("test", ("mix", "test")),
    # type checks
    ("typecheck", ("mypy",)),
    ("typecheck", ("pyright",)),
    ("typecheck", ("tsc",)),
    ("typecheck", ("npx", "tsc")),
    ("typecheck", ("deno", "check")),
    # linters ("ruff" alone is lint; "ruff format" matches the longer
    # formatter prefix below)
    ("lint", ("ruff",)),
    ("lint", ("flake8",)),
    ("lint", ("pylint",)),
    ("lint", ("eslint",)),
    ("lint", ("npx", "eslint")),
    ("lint", ("npm", "run", "lint")),
    ("lint", ("cargo", "clippy")),
    ("lint", ("golangci-lint",)),
    ("lint", ("go", "vet")),
    ("lint", ("shellcheck",)),
    ("lint", ("hadolint",)),
    # formatters (listed after lint but matched by longest prefix)
    ("format", ("ruff", "format")),
    ("format", ("black",)),
    ("format", ("isort",)),
    ("format", ("prettier",)),
    ("format", ("npx", "prettier")),
    ("format", ("gofmt",)),
    ("format", ("cargo", "fmt")),
    ("format", ("swiftformat",)),
    # builds
    ("build", ("cargo", "build")),
    ("build", ("go", "build")),
    ("build", ("npm", "run", "build")),
    ("build", ("yarn", "build")),
    ("build", ("pnpm", "build")),
    ("build", ("make", "build")),
    ("build", ("make",)),
    ("build", ("docker", "build")),
    ("build", ("python", "-m", "build")),
    ("build", ("python3", "-m", "build")),
    ("build", ("xcodebuild",)),
    ("build", ("mvn", "package")),
    ("build", ("dotnet", "build")),
)


@dataclass(frozen=True)
class Check:
    """One distinct verification command observed in the journal."""

    category: str
    command: str
    exit_code: Optional[int]
    runs: int

    @property
    def passed(self) -> Optional[bool]:
        if self.exit_code is None:
            return None
        return self.exit_code == 0

    @property
    def outcome(self) -> str:
        """Human label for the last recorded result."""
        if self.exit_code is None:
            return "no result recorded"
        if self.exit_code == 0:
            return "pass (exit 0)"
        return f"FAIL (exit {self.exit_code})"


def normalize_command(command: str) -> str:
    """Strip env-var assignments and prefix wrappers; collapse whitespace.

    ``CI=1 time python -m pytest -q`` and ``python -m pytest  -q`` both
    normalize to ``python -m pytest -q``, so re-runs dedupe correctly.
    """
    tokens = command.split()
    while tokens and _ENV_ASSIGNMENT_RE.match(tokens[0]):
        tokens.pop(0)
    while tokens and tokens[0] in ("time", "env", "nice", "command"):
        tokens.pop(0)
        # `env FOO=bar cmd` — keep stripping assignments after the wrapper.
        while tokens and _ENV_ASSIGNMENT_RE.match(tokens[0]):
            tokens.pop(0)
    return " ".join(tokens)


def classify_command(command: str) -> Optional[str]:
    """Return the check category for a command, or None if it is not a check.

    A command mentioning ``smoke`` (e.g. ``bash scripts/smoke.sh``) counts
    as a test: smoke scripts are the CI substitute in many local-first repos.
    """
    normalized = normalize_command(command)
    if not normalized:
        return None
    tokens = tuple(normalized.split())
    best: Optional[Tuple[int, str]] = None
    for category, prefix in _RULES:
        if len(prefix) <= len(tokens) and tuple(tokens[: len(prefix)]) == prefix:
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), category)
    if best is not None:
        return best[1]
    if "smoke" in normalized and tokens[0] in ("bash", "sh"):
        return "test"
    if tokens[0].endswith("/smoke.sh") or tokens[0] == "smoke.sh":
        return "test"
    return None


def collect_checks(events: Iterable[JournalEvent]) -> List[Check]:
    """Fold command events into a deduplicated, ordered list of checks.

    Dedup key is the normalized command string. For each key we keep the
    exit code of the **last** occurrence and count total runs. Output order
    is (category order, first occurrence) — stable for identical input.
    """
    state: Dict[str, Dict[str, object]] = {}
    order: List[str] = []
    for event in events:
        if event.kind != "command":
            continue
        category = classify_command(event.text)
        if category is None:
            continue
        key = normalize_command(event.text)
        if key not in state:
            state[key] = {"category": category, "exit": event.exit_code, "runs": 0}
            order.append(key)
        entry = state[key]
        entry["runs"] = int(entry["runs"]) + 1  # type: ignore[arg-type]
        entry["exit"] = event.exit_code  # last occurrence wins

    def sort_key(key: str) -> Tuple[int, int]:
        category = str(state[key]["category"])
        try:
            rank = CATEGORY_ORDER.index(category)
        except ValueError:  # pragma: no cover - all rules use known categories
            rank = len(CATEGORY_ORDER)
        return (rank, order.index(key))

    checks: List[Check] = []
    for key in sorted(order, key=sort_key):
        entry = state[key]
        checks.append(
            Check(
                category=str(entry["category"]),
                command=key,
                exit_code=entry["exit"],  # type: ignore[arg-type]
                runs=int(entry["runs"]),  # type: ignore[arg-type]
            )
        )
    return checks
