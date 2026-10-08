import json
import subprocess
from pathlib import Path

import pytest

import ledger
from helpers import git
from sequences import CONFIG

CALL: ledger.Call = {"session": "s1", "agent": None, "tool": "Bash", "call": "toolu_1"}


def chain(repo: Path) -> list[str]:
    return git(repo, "rev-list", ledger.REF).splitlines()


def test_the_first_record_of_a_worktree_has_no_parent(repo: Path) -> None:
    record = ledger.record(repo, CALL, CONFIG)
    assert record is not None

    assert chain(repo) == [record]
    assert git(repo, "rev-list", "--parents", "-n1", record) == record


def test_an_unchanged_tree_adds_no_record(repo: Path) -> None:
    first = ledger.record(repo, CALL, CONFIG)

    assert ledger.record(repo, CALL, CONFIG) is None
    assert chain(repo) == [first]


def test_a_changed_tree_is_recorded_on_top_of_the_previous(repo: Path) -> None:
    first = ledger.record(repo, CALL, CONFIG)
    (repo / "src" / "a.py").write_text("A = 2\n")

    second = ledger.record(repo, CALL, CONFIG)

    assert chain(repo) == [second, first]
    assert git(repo, "rev-parse", f"{second}^") == first


def message(repo: Path, record: str) -> dict[str, object]:
    fields: dict[str, object] = json.loads(git(repo, "log", "-1", "--format=%B", record))
    return fields


def test_the_message_names_the_call_its_time_branch_and_head(repo: Path) -> None:
    record = ledger.record(repo, CALL, CONFIG)
    assert record is not None

    fields = message(repo, record)

    assert set(fields) == {"time", "session", "agent", "tool", "call", "branch", "head"}
    assert fields["session"] == "s1"
    assert fields["agent"] is None
    assert fields["tool"] == "Bash"
    assert fields["call"] == "toolu_1"
    assert fields["branch"] == "main"
    assert fields["head"] == git(repo, "rev-parse", "HEAD")
    assert isinstance(fields["time"], str)
    assert fields["time"].endswith("Z")


def test_a_detached_head_records_no_branch(repo: Path) -> None:
    git(repo, "checkout", "-q", "--detach")
    record = ledger.record(repo, CALL, CONFIG)
    assert record is not None

    assert message(repo, record)["branch"] is None


def test_a_concurrent_record_is_kept_and_the_append_retried(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = ledger.record(repo, CALL, CONFIG)
    (repo / "src" / "a.py").write_text("A = 2\n")
    real_git = ledger.git
    raced: list[str] = []

    def racing_git(
        worktree: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None
    ) -> str:
        if args[0] == "update-ref" and not raced:
            # Another hook appends its record between this one's read and its write.
            other = real_git(
                worktree, "commit-tree", f"{first}^{{tree}}", "-p", str(first), "-m", "{}"
            )
            real_git(worktree, "update-ref", ledger.REF, other)
            raced.append(other)
        return real_git(worktree, *args, env=env, input=input)

    monkeypatch.setattr(ledger, "git", racing_git)

    mine = ledger.record(repo, CALL, CONFIG)

    assert chain(repo) == [mine, raced[0], first]


def test_losing_every_race_is_an_error_not_a_lost_record(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger.record(repo, CALL, CONFIG)
    (repo / "src" / "a.py").write_text("A = 2\n")
    real_git = ledger.git

    def always_racing(
        worktree: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None
    ) -> str:
        if args[0] == "update-ref":
            # What update-ref says when the ref moved since it was read.
            raise subprocess.CalledProcessError(
                128, "git update-ref", stderr="fatal: cannot lock ref: is at x but expected y"
            )
        return real_git(worktree, *args, env=env, input=input)

    monkeypatch.setattr(ledger, "git", always_racing)

    with pytest.raises(ledger.RecordError, match="5 attempts"):
        ledger.record(repo, CALL, CONFIG)


def test_a_linked_worktree_keeps_its_own_ledger(repo: Path, tmp_path: Path) -> None:
    main_record = ledger.record(repo, CALL, CONFIG)
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "other", str(linked))
    (linked / "src" / "a.py").write_text("A = 9\n")

    linked_record = ledger.record(linked, CALL, CONFIG)

    assert chain(repo) == [main_record]
    assert chain(linked) == [linked_record]


def test_records_survive_garbage_collection(repo: Path) -> None:
    first = ledger.record(repo, CALL, CONFIG)
    (repo / "src" / "a.py").write_text("A = 2\n")
    second = ledger.record(repo, CALL, CONFIG)

    git(repo, "gc", "-q", "--prune=now")

    assert chain(repo) == [second, first]
    assert git(repo, "cat-file", "-t", f"{first}^{{tree}}") == "tree"


def test_a_held_lock_is_reported_as_such_not_as_a_lost_race(repo: Path) -> None:
    ledger.record(repo, CALL, CONFIG)
    lock = repo / ".git" / "refs" / "worktree" / "test-first" / "ledger.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("held\n")
    (repo / "src" / "a.py").write_text("A = 2\n")

    with pytest.raises(ledger.RecordError, match="lock"):
        ledger.record(repo, CALL, CONFIG)


def test_a_linked_worktrees_records_survive_gc_run_from_another_worktree(
    repo: Path, tmp_path: Path
) -> None:
    # git 2.55 does not count other worktrees' refs/worktree/* as reachable (research R2).
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "other", str(linked))
    first = ledger.record(linked, CALL, CONFIG)
    (linked / "src" / "a.py").write_text("A = 9\n")
    second = ledger.record(linked, CALL, CONFIG)

    git(repo, "gc", "-q", "--prune=now")

    assert chain(linked) == [second, first]
    assert git(linked, "cat-file", "-t", f"{first}^{{tree}}") == "tree"


def test_a_removed_worktrees_ledger_is_pruned_when_another_ledger_is_created(
    repo: Path, tmp_path: Path
) -> None:
    kept, removed = tmp_path / "kept", tmp_path / "removed"
    git(repo, "worktree", "add", "-q", "-b", "kept", str(kept))
    git(repo, "worktree", "add", "-q", "-b", "removed", str(removed))
    ledger.record(kept, CALL, CONFIG)
    ledger.record(removed, CALL, CONFIG)
    assert len(git(repo, "for-each-ref", "refs/test-first/").splitlines()) == 2
    git(repo, "worktree", "remove", "--force", str(removed))

    ledger.record(repo, CALL, CONFIG)

    ledgers = git(repo, "for-each-ref", "--format=%(refname)", "refs/test-first/").splitlines()
    assert sorted(ledgers) == sorted(
        [
            git(kept, "symbolic-ref", ledger.REF),
            git(repo, "symbolic-ref", ledger.REF),
        ]
    )
