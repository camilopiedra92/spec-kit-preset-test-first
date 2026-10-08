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


def orphan_then(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, race: str) -> str:
    """A removed worktree's ledger, which `race` changes right after the next creation lists it:
    as another worktree's prune would ("delete"), or as a writer would ("move")."""
    gone = tmp_path / "gone"
    git(repo, "worktree", "add", "-q", "-b", "gone", str(gone))
    ledger.record(gone, CALL, CONFIG)
    name = git(gone, "symbolic-ref", ledger.REF)
    git(repo, "worktree", "remove", "--force", str(gone))
    real_git = ledger.git

    def racing(worktree: Path, *args: str, **kwargs: object) -> str:
        listed = real_git(worktree, *args, **kwargs)  # type: ignore[arg-type]
        if args[0] == "for-each-ref" and listed:
            if race == "delete":
                real_git(worktree, "update-ref", "-d", name)
            else:
                moved = real_git(worktree, "commit-tree", f"{name}^{{tree}}", "-m", "moved")
                real_git(worktree, "update-ref", name, moved)
        return listed

    monkeypatch.setattr(ledger, "git", racing)
    return name


def test_an_orphan_another_worktree_pruned_first_does_not_fail_the_record(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    orphan_then(repo, tmp_path, monkeypatch, "delete")

    assert ledger.record(repo, CALL, CONFIG) is not None


def test_an_orphan_that_moved_after_it_was_listed_is_not_deleted(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = orphan_then(repo, tmp_path, monkeypatch, "move")

    assert ledger.record(repo, CALL, CONFIG) is not None
    assert git(repo, "for-each-ref", "--format=%(refname)", name) == name


def test_a_worktree_name_git_cannot_read_stops_the_prune_instead_of_taking_an_orphan(
    repo: Path, tmp_path: Path
) -> None:
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "linked", str(linked))
    ledger.record(linked, CALL, CONFIG)
    live = git(linked, "symbolic-ref", ledger.REF)
    name = repo / ".git" / "worktrees" / "linked" / "refs" / "worktree" / "test-first" / "ledger"
    name.chmod(0)  # git: "No such ref", exit 128 -- not "absent", exit 1
    try:
        with pytest.raises(ledger.RecordError):
            ledger.record(repo, CALL, CONFIG)
    finally:
        name.chmod(0o644)

    assert git(repo, "for-each-ref", "--format=%(refname)", live) == live


def test_a_name_left_dangling_by_a_killed_run_is_where_the_first_record_lands(
    repo: Path,
) -> None:
    left = ledger.LEDGERS + "left-by-a-killed-run"
    git(repo, "symbolic-ref", ledger.REF, left)  # named, but its first record never landed

    first = ledger.record(repo, CALL, CONFIG)

    assert git(repo, "rev-parse", left) == first
