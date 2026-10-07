"""Ledgers built call by call, for the audit's units."""

import sys
from pathlib import Path

import ledger
from helpers import git

FAKE_RUNNER = Path(__file__).with_name("fake_runner.py")
CONFIG = ledger.Config(
    tests=("tests/**",),
    sources=("src/**",),
    run=f"{sys.executable} {FAKE_RUNNER} {{file}} {{junit}}",
)


# A run whose code comes from the real worktree, not the replayed tree (an editable install).
LEAKING = CONFIG._replace(run=CONFIG.run + " --root {root}")


def snapshot(repo: Path) -> str:
    """The worktree's tree as the ledger snapshots it: recorded, then read from the ledger."""
    call: ledger.Call = {"session": "s", "agent": None, "tool": "Bash", "call": None}
    ledger.record(repo, call, CONFIG)
    return git(repo, "rev-parse", f"{ledger.REF}^{{tree}}")


class Calls:
    """Applies one tool call's writes to the worktree and records it in the ledger."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.count = 0

    def call(self, files: dict[str, str | None], commit: bool = False) -> str:
        """Write (or, for None, delete) each file, commit when asked (in the same call), then
        record the call; its record."""
        for name, content in files.items():
            path = self.repo / name
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
        if commit:
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", f"call {self.count + 1}")
        self.count += 1
        call: ledger.Call = {
            "session": "s",
            "agent": None,
            "tool": "Bash",
            "call": f"c{self.count}",
        }
        made = ledger.record(self.repo, call, CONFIG)
        assert made is not None, "a call in a sequence must change the worktree"
        return made
