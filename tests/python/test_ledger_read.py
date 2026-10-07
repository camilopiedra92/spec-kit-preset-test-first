from pathlib import Path

import audit
import ledger
from helpers import git

CALL: ledger.Call = {"session": "s", "agent": None, "tool": "Bash", "call": "t"}


def test_the_ledger_reads_back_oldest_first_with_branch_and_head(repo: Path) -> None:
    first = ledger.record(repo, CALL)
    (repo / "src" / "a.py").write_text("A = 2\n")
    second = ledger.record(repo, CALL)

    read = audit.load_records(repo)

    head = git(repo, "rev-parse", "HEAD")
    assert read == [
        audit.Record(
            str(first), git(repo, "rev-parse", f"{first}^{{tree}}"), "main", head, "Bash", "t"
        ),
        audit.Record(
            str(second), git(repo, "rev-parse", f"{second}^{{tree}}"), "main", head, "Bash", "t"
        ),
    ]


def test_no_ledger_reads_as_no_records(repo: Path) -> None:
    assert audit.load_records(repo) == []


def test_a_change_is_the_paths_that_differ(repo: Path) -> None:
    before = ledger.snapshot(repo)
    (repo / "src" / "a.py").write_text("A = 2\n")
    (repo / "tests" / "test_a.py").unlink()
    (repo / "src" / "año.py").write_text("new\n")
    after = ledger.snapshot(repo)

    assert audit.changed_paths(repo, before, after) == {"src/a.py", "tests/test_a.py", "src/año.py"}
