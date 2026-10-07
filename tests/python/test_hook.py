import json
from pathlib import Path

import pytest

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


def test_a_call_changing_a_test_and_a_source_is_told_with_both_named(repo: Path) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))  # the origin
    (repo / "tests" / "test_a.py").write_text("def test_a(): assert True\n")
    (repo / "src" / "a.py").write_text("A = 2\n")

    status, stderr = ledger.post_tool_use(payload(repo))

    assert status == 2
    assert "tests/test_a.py" in stderr
    assert "src/a.py" in stderr


@pytest.mark.parametrize(
    "files",
    [
        {"tests/test_a.py": "def test_a(): assert True\n"},
        {"src/a.py": "A = 2\n"},
        {"tests/test_a.py": "def test_a(): assert True\n", "README.md": "docs\n"},
    ],
)
def test_a_call_that_is_not_mixed_is_silent(repo: Path, files: dict[str, str]) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))  # the origin
    for name, content in files.items():
        (repo / name).write_text(content)

    assert ledger.post_tool_use(payload(repo)) == (0, "")


def test_an_unchanged_worktree_is_silent(repo: Path) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))

    assert ledger.post_tool_use(payload(repo)) == (0, "")


def test_the_message_is_conditional_and_names_the_redo(repo: Path) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))
    (repo / "tests" / "test_a.py").write_text("def test_renamed(): pass\n")
    (repo / "src" / "a.py").write_text("RENAMED = 1\n")

    _, raw = ledger.post_tool_use(payload(repo))
    stderr = " ".join(raw.lower().split())  # the content, not where its lines break

    assert "if this call added or changed a test together with the code" in stderr
    assert "the audit will fail" in stderr
    assert "a rename or a formatter run" in stderr
    assert "revert the code" in stderr
