import time
from pathlib import Path

from helpers import git
from sequences import snapshot


def test_a_clean_repository_snapshots_to_heads_tree(repo: Path) -> None:
    assert snapshot(repo) == git(repo, "rev-parse", "HEAD^{tree}")


def paths(repo: Path, tree: str) -> set[str]:
    return set(git(repo, "ls-tree", "-r", "--name-only", tree).splitlines())


def test_untracked_files_are_in_the_tree_and_ignored_ones_are_not(repo: Path) -> None:
    (repo / ".gitignore").write_text("*.log\n")
    (repo / "src" / "new.py").write_text("B = 2\n")
    (repo / "debug.log").write_text("noise\n")

    tree = paths(repo, snapshot(repo))

    assert "src/new.py" in tree
    assert "debug.log" not in tree


def test_a_deleted_tracked_file_is_absent(repo: Path) -> None:
    (repo / "src" / "a.py").unlink()

    assert "src/a.py" not in paths(repo, snapshot(repo))


def test_staged_and_unstaged_edits_give_the_worktrees_content(repo: Path) -> None:
    (repo / "src" / "a.py").write_text("A = 2\n")
    git(repo, "add", "src/a.py")
    (repo / "src" / "a.py").write_text("A = 3\n")

    tree = snapshot(repo)

    assert git(repo, "show", f"{tree}:src/a.py") == "A = 3"


def test_the_real_index_and_the_status_are_left_untouched(repo: Path) -> None:
    (repo / "src" / "a.py").write_text("A = 2\n")
    (repo / "src" / "new.py").write_text("B = 2\n")
    git(repo, "add", "src/a.py")
    # status first: it refreshes the real index's stat data itself.
    status_before = git(repo, "status", "--porcelain")
    index_before = (repo / ".git" / "index").read_bytes()

    snapshot(repo)

    assert (repo / ".git" / "index").read_bytes() == index_before
    assert git(repo, "status", "--porcelain") == status_before


def test_a_same_size_edit_in_the_index_writes_second_is_seen(repo: Path) -> None:
    # git trusts an entry's stat unless the entry is not older than the index file ("racy
    # git"); the snapshot's copy of the index must keep the index's mtime for that check to
    # hold. The edit lands in the commit's second; the snapshot starts in the next one.
    (repo / "src" / "a.py").write_text("A = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "rewrite the index now")
    (repo / "src" / "a.py").write_text("A = 2\n")
    time.sleep(1.05 - time.time() % 1)

    tree = snapshot(repo)

    assert git(repo, "show", f"{tree}:src/a.py") == "A = 2"


def test_a_tracked_file_that_gitignore_matches_is_still_recorded(repo: Path) -> None:
    (repo / "keep.log").write_text("tracked on purpose\n")
    git(repo, "add", "keep.log")
    git(repo, "commit", "-q", "-m", "track a log")
    (repo / ".gitignore").write_text("*.log\n")

    assert "keep.log" in paths(repo, snapshot(repo))
