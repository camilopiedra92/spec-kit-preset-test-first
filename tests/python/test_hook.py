import json
from pathlib import Path

import ledger
from helpers import git


def payload(cwd: Path, **extra: str) -> dict[str, str]:
    return {
        "cwd": str(cwd),
        "session_id": "s1",
        "tool_name": "Bash",
        "tool_use_id": "toolu_1",
        **extra,
    }


def test_outside_a_git_repository_it_does_nothing(tmp_path: Path) -> None:
    assert ledger.post_tool_use(payload(tmp_path)) == (0, "")


def install(repo: Path) -> None:
    (repo / ".specify").mkdir()
    (repo / ".specify" / "test-first.json").write_text(
        json.dumps({"tests": ["tests/**"], "sources": ["src/**"], "run": "x {file} {junit}"})
    )


def newest_message(repo: Path) -> dict[str, object]:
    fields: dict[str, object] = json.loads(git(repo, "log", "-1", "--format=%B", ledger.REF))
    return fields


def test_installed_a_changed_worktree_is_recorded_with_the_call(repo: Path) -> None:
    install(repo)
    (repo / "src" / "a.py").write_text("A = 2\n")

    assert ledger.post_tool_use(payload(repo)) == (0, "")

    fields = newest_message(repo)
    assert (fields["session"], fields["tool"], fields["call"]) == ("s1", "Bash", "toolu_1")


def test_a_repository_without_the_configuration_records_nothing(repo: Path) -> None:
    (repo / "src" / "a.py").write_text("A = 2\n")

    assert ledger.post_tool_use(payload(repo)) == (0, "")
    assert git(repo, "for-each-ref", ledger.REF) == ""


def test_a_subagents_call_carries_its_agent_id(repo: Path) -> None:
    install(repo)
    (repo / "src" / "a.py").write_text("A = 2\n")

    ledger.post_tool_use(payload(repo, agent_id="agent-7"))

    assert newest_message(repo)["agent"] == "agent-7"


def test_a_cwd_below_the_root_records_into_its_worktree(repo: Path, tmp_path: Path) -> None:
    install(repo)
    git(repo, "add", ".specify")
    git(repo, "commit", "-q", "-m", "install")
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-q", "-b", "other", str(linked))
    (linked / "src" / "a.py").write_text("A = 9\n")

    ledger.post_tool_use(payload(linked / "src"))

    assert git(linked, "rev-parse", "--verify", "-q", ledger.REF) != ""
    assert git(repo, "for-each-ref", ledger.REF) == ""


def test_a_malformed_configuration_is_reported_and_nothing_recorded(repo: Path) -> None:
    (repo / ".specify").mkdir()
    (repo / ".specify" / "test-first.json").write_text('{"tests": []}')

    status, stderr = ledger.post_tool_use(payload(repo))

    assert status == 2
    assert "test-first.json" in stderr
    assert "tests" in stderr
    assert git(repo, "for-each-ref", ledger.REF) == ""


def test_a_git_failure_is_reported_and_the_repository_left_as_found(repo: Path) -> None:
    install(repo)
    (repo / "src" / "new.py").write_text("B = 2\n")
    status_before = git(repo, "status", "--porcelain")
    index_before = (repo / ".git" / "index").read_bytes()
    objects = repo / ".git" / "objects"
    modes = {path: path.stat().st_mode for path in [objects, *objects.rglob("*")]}
    for path in modes:
        path.chmod(0o555 if path.is_dir() else 0o444)
    try:
        status, stderr = ledger.post_tool_use(payload(repo))
    finally:
        for path, mode in modes.items():
            path.chmod(mode)

    assert status == 2
    assert "test-first ledger" in stderr
    assert "insufficient permission" in stderr or "Permission denied" in stderr
    assert git(repo, "status", "--porcelain") == status_before
    assert (repo / ".git" / "index").read_bytes() == index_before
