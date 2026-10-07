from pathlib import Path

import pytest

import audit
from helpers import git


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


def with_origin(repo: Path, tmp_path: Path, set_head: bool = True) -> str:
    """Publish main to a bare origin and fetch it back; return main's commit."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    if set_head:
        git(repo, "remote", "set-head", "origin", "main")
    else:
        # git 2.48+ creates origin/HEAD on fetch (remote.origin.followRemoteHEAD): undo it.
        git(repo, "remote", "set-head", "origin", "--delete")
    return git(repo, "rev-parse", "main")


def on_feature(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    commit(repo, "feature.txt")


def test_the_base_is_the_merge_base_with_the_branch_origin_head_names(
    repo: Path, tmp_path: Path
) -> None:
    main = with_origin(repo, tmp_path)
    on_feature(repo)

    assert audit.resolve_base(repo) == main


def test_without_origin_head_origin_main_is_the_default(repo: Path, tmp_path: Path) -> None:
    main = with_origin(repo, tmp_path, set_head=False)
    on_feature(repo)

    assert audit.resolve_base(repo) == main


def test_without_a_remote_the_local_main_is_the_default(repo: Path) -> None:
    main = git(repo, "rev-parse", "main")
    on_feature(repo)

    assert audit.resolve_base(repo) == main


def test_a_local_merge_into_main_does_not_move_the_base(repo: Path, tmp_path: Path) -> None:
    main = with_origin(repo, tmp_path)
    on_feature(repo)
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--ff-only", "feat")
    git(repo, "checkout", "-q", "feat")

    assert audit.resolve_base(repo) == main


def test_head_on_the_default_branch_is_refused(repo: Path, tmp_path: Path) -> None:
    with_origin(repo, tmp_path)

    with pytest.raises(audit.BaseError, match=r"default branch.*main"):
        audit.resolve_base(repo)


def test_nothing_resolving_is_refused_naming_what_was_tried(repo: Path) -> None:
    git(repo, "branch", "-m", "trunk")
    on_feature(repo)

    with pytest.raises(audit.BaseError, match=r"main.*master"):
        audit.resolve_base(repo)


def test_an_explicit_base_is_that_commit(repo: Path) -> None:
    on_feature(repo)
    feature_start = git(repo, "rev-parse", "HEAD")
    commit(repo, "more.txt")

    assert audit.resolve_base(repo, override="HEAD~1") == feature_start


def test_the_base_comes_from_local_refs_without_fetching(repo: Path, tmp_path: Path) -> None:
    main = with_origin(repo, tmp_path)
    # The remote's main moves on; a fetch would bring that into origin/main and move the base.
    moved = tmp_path / "moved"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(moved))
    git(moved, "config", "user.email", "t@example.com")
    git(moved, "config", "user.name", "T")
    commit(moved, "upstream.txt")
    git(moved, "push", "-q", "origin", "main")
    on_feature(repo)

    assert audit.resolve_base(repo) == main
    assert git(repo, "rev-parse", "origin/main") == main, "the audit fetched"


def test_without_a_remote_the_configured_default_branch_comes_first(repo: Path) -> None:
    git(repo, "branch", "-m", "trunk")
    git(repo, "config", "init.defaultBranch", "trunk")
    trunk = git(repo, "rev-parse", "trunk")
    on_feature(repo)
    # A main taken from the feature: its merge base with the feature is the feature's tip, so
    # taking main instead of the configured default would give a different base.
    git(repo, "branch", "main")
    commit(repo, "more.txt")

    assert audit.resolve_base(repo) == trunk


def test_an_explicit_base_is_honoured_on_the_default_branch(repo: Path) -> None:
    first = git(repo, "rev-parse", "HEAD")
    commit(repo, "merged.txt")

    assert audit.resolve_base(repo, override=first) == first
