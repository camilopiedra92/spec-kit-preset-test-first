import json
import subprocess
from pathlib import Path

import pytest

import ledger
from helpers import git
from sequences import CONFIG


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


def test_an_unborn_branch_is_recorded_with_no_head(repo: Path) -> None:
    install(repo)
    git(repo, "checkout", "-q", "--orphan", "fresh")
    (repo / "src" / "a.py").write_text("A = 2\n")

    assert ledger.post_tool_use(payload(repo)) == (0, "")
    fields = newest_message(repo)
    assert (fields["branch"], fields["head"]) == ("fresh", None)


def test_a_reftable_repository_records_its_branch(tmp_path: Path) -> None:
    repo = tmp_path / "reftable"
    git(tmp_path, "init", "-q", "--ref-format=reftable", "-b", "feat", str(repo))
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "T")
    (repo / "src").mkdir()
    (repo / "src" / "a.py").write_text("A = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    install(repo)
    (repo / "src" / "a.py").write_text("A = 2\n")

    ledger.post_tool_use(payload(repo))

    assert newest_message(repo)["branch"] == "feat"


def install_with(repo: Path, tests: list[str], sources: list[str]) -> None:
    (repo / ".specify").mkdir()
    (repo / ".specify" / "test-first.json").write_text(
        json.dumps({"tests": tests, "sources": sources, "run": "x {file} {junit}"})
    )


def test_the_hook_and_the_audit_agree_on_globs_without_wildcards(repo: Path) -> None:
    # git's pathspecs read "tests" as a directory prefix; the configuration's globs do not.
    install_with(repo, ["tests"], ["src"])
    ledger.post_tool_use(payload(repo))
    (repo / "tests" / "test_b.py").write_text("def test_b(): pass\n")
    (repo / "src" / "b.py").write_text("B = 1\n")

    assert ledger.post_tool_use(payload(repo)) == (0, "")


def test_each_path_is_named_once_in_its_own_group(repo: Path) -> None:
    install_with(repo, ["**/test_*.py"], ["src/**"])
    ledger.post_tool_use(payload(repo))
    (repo / "src" / "test_x.py").write_text("def test_x(): pass\n")  # both globs: a test
    (repo / "src" / "b.py").write_text("B = 1\n")

    _, stderr = ledger.post_tool_use(payload(repo))

    lines = stderr.splitlines()
    assert "  tests: src/test_x.py" in lines
    assert "  code:  src/b.py" in lines


def test_a_code_only_call_then_a_test_only_call_is_silent(repo: Path) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))
    (repo / "src" / "a.py").write_text("A = 2\n")
    ledger.post_tool_use(payload(repo))
    (repo / "tests" / "test_a.py").write_text("def test_a(): assert 1\n")

    assert ledger.post_tool_use(payload(repo)) == (0, "")


def test_after_a_lost_race_the_change_is_against_the_record_that_won(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))  # R0, the origin
    origin = git(repo, "rev-parse", ledger.REF)
    (repo / "tests" / "test_b.py").write_text("def test_b(): pass\n")
    # What another hook records first, the test alone; held back until this call's update-ref.
    other = ledger.record(
        repo, {"session": "s", "agent": None, "tool": "Bash", "call": "x"}, CONFIG
    )
    git(repo, "update-ref", ledger.REF, origin)
    (repo / "src" / "b.py").write_text("B = 1\n")  # this call's own write: the code
    real_git = ledger.git
    raced: list[bool] = []

    def racing_git(
        worktree: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None
    ) -> str:
        if args[0] == "update-ref" and not raced:
            real_git(worktree, "update-ref", ledger.REF, str(other))
            raced.append(True)
        return real_git(worktree, *args, env=env, input=input)

    monkeypatch.setattr(ledger, "git", racing_git)

    assert ledger.post_tool_use(payload(repo)) == (0, "")


def kept_index(repo: Path) -> Path:
    return Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "test-first/index"))


def test_a_copy_left_by_a_killed_hook_is_pruned(repo: Path) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))
    finished = subprocess.Popen(["true"])
    finished.wait()  # reaped: its pid names no process
    left = kept_index(repo).with_name(f"index.{finished.pid}.new")
    left.write_text("half-written\n")

    ledger.post_tool_use(payload(repo))

    assert not left.exists()
    assert list(kept_index(repo).parent.glob("index.*.new")) == []


def test_a_change_whose_record_failed_is_shown_by_the_next_call(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(repo)
    ledger.post_tool_use(payload(repo))
    (repo / "tests" / "test_b.py").write_text("def test_b(): pass\n")
    (repo / "src" / "b.py").write_text("B = 1\n")
    real_git = ledger.git

    def failing_update_ref(
        worktree: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None
    ) -> str:
        if args[0] == "update-ref":
            raise subprocess.CalledProcessError(128, "git", stderr="fatal: disk full")
        return real_git(worktree, *args, env=env, input=input)

    monkeypatch.setattr(ledger, "git", failing_update_ref)
    assert ledger.post_tool_use(payload(repo))[0] == 2
    monkeypatch.setattr(ledger, "git", real_git)

    status, stderr = ledger.post_tool_use(payload(repo))

    assert status == 2
    assert "src/b.py" in stderr
