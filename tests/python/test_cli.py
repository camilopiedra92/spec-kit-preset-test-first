import io
import json
import subprocess
from pathlib import Path

import pytest

import audit
from helpers import git
from sequences import CONFIG, Calls

TEST_B = "def test_b(): # expects src/b.py B\n"


def install(repo: Path) -> None:
    (repo / ".specify").mkdir(exist_ok=True)
    (repo / ".specify" / "test-first.json").write_text(json.dumps(CONFIG._asdict()))
    git(repo, "add", ".specify")
    git(repo, "commit", "-q", "-m", "install")


def feature(repo: Path) -> Calls:
    install(repo)
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    return calls


def run(repo: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> int:
    monkeypatch.chdir(repo)
    return audit.main(["--deadline", "30", *args])


def test_an_edit_made_after_the_last_call_is_recorded_before_judging(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    (repo / "src" / "b.py").write_text("B\n")  # by hand, between calls

    run(repo, monkeypatch)

    newest = json.loads(git(repo, "log", "-1", "--format=%B", "refs/worktree/test-first/ledger"))
    assert newest["tool"] == "audit"


def test_refusals_exit_2_with_a_message(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    assert run(repo, monkeypatch) == 2
    assert "not installed" in capsys.readouterr().err

    install(repo)
    assert run(repo, monkeypatch) == 2
    assert "no ledger" in capsys.readouterr().err

    Calls(repo).call({"README.md": "origin"})
    git(repo, "checkout", "-q", "--detach")
    assert run(repo, monkeypatch) == 2
    assert "detached" in capsys.readouterr().err

    git(repo, "checkout", "-q", "-B", "main", "feat")  # main, with the configuration
    assert run(repo, monkeypatch) == 2
    assert "default branch" in capsys.readouterr().err


def test_the_report_names_each_test_its_record_and_call_and_ends_with_a_summary(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    green = calls.call({"src/b.py": "B\n"})
    mixed = calls.call(
        {"tests/test_c.py": "def test_c(): # expects src/c.py C\n", "src/c.py": "C\n"}
    )

    status = run(repo, monkeypatch)

    lines = capsys.readouterr().out.splitlines()
    assert status == 1
    # c1 is the origin's call.
    assert f"born-with-code tests.test_c::test_c {mixed} Bash c4" in lines
    assert f"red tests.test_b::test_b {green} Bash c3" in lines
    assert lines[-1] == "audit: 2 new tests: born-with-code 1, red 1; FAIL"


def test_a_failing_verdict_is_followed_by_its_remedy(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})

    run(repo, monkeypatch)

    out = capsys.readouterr().out
    assert "remove the test" in out
    assert "revert the code it covers" in out


def test_a_tasks_file_claiming_red_runs_changes_nothing(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})
    calls.call({"specs/001/tasks.md": "- [X] T001\n  - test_b\n    - red: `pytest` -> 1 failed\n"})

    assert run(repo, monkeypatch) == 1
    assert "born-with-code tests.test_b::test_b" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("name", "phrase"),
    [
        ("rewritten-to-green", "redo it"),
        ("still-red", "write the code that makes it pass"),
        ("unobserved", "gives it a birth in this ledger"),
        ("born-green", "redo it"),
    ],
)
def test_every_failing_verdict_without_a_reason_prints_its_remedy(name: str, phrase: str) -> None:
    printed = audit.render([("t::x", audit.Verdict(name))], {})

    assert phrase in printed


def test_without_the_preset_runner_the_audit_refuses_naming_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feature(repo).call({"tests/test_b.py": TEST_B})
    monkeypatch.setattr(audit, "RUNNER", repo / "missing" / "run-bounded.sh")

    assert run(repo, monkeypatch) == 2
    assert "run-bounded.sh" in capsys.readouterr().err


def test_a_git_error_during_the_audit_exits_2_with_its_message(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feature(repo).call({"tests/test_b.py": TEST_B})
    lock = Path(
        git(
            repo,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "refs/worktree/test-first/ledger.lock",
        )
    )
    lock.write_text("held\n")
    (repo / "src" / "b.py").write_text("B\n")  # the audit must record it first

    assert run(repo, monkeypatch) == 2
    err = capsys.readouterr().err
    assert err.startswith("test-first audit:")
    assert "Traceback" not in err


def test_a_file_system_error_during_the_audit_exits_2_with_its_message(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feature(repo).call({"tests/test_b.py": TEST_B})

    def no_space(*args: object, **kwargs: object) -> str:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("tempfile.mkdtemp", no_space)

    assert run(repo, monkeypatch) == 2
    assert "No space left on device" in capsys.readouterr().err


def test_a_base_git_cannot_resolve_is_a_refusal_with_its_message(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feature(repo).call({"tests/test_b.py": TEST_B})

    assert run(repo, monkeypatch, "--base", "nosuchrev") == 2
    err = capsys.readouterr().err
    assert err.startswith("test-first audit:") and "nosuchrev" in err


def test_a_branch_with_no_common_ancestor_is_a_refusal(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install(repo)
    git(repo, "checkout", "-q", "--orphan", "lonely")
    git(repo, "commit", "-q", "-m", "unrelated history")
    Calls(repo).call({"README.md": "origin"})

    assert run(repo, monkeypatch) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_a_branch_created_without_a_tree_change_is_judged_on_the_line_it_came_from(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})
    git(repo, "checkout", "-q", "-b", "feat2")  # the same tree: no record on feat2

    assert run(repo, monkeypatch) == 0
    assert capsys.readouterr().out.startswith("red tests.test_b::test_b ")

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": str(repo), "session_id": "s"})))
    assert audit.main(["--stop"]) == 0


def git_processes_of_an_audit(
    repo: Path, monkeypatch: pytest.MonkeyPatch, records_before: int
) -> int:
    calls = feature(repo)
    for i in range(records_before):
        calls.call({"notes.txt": str(i)})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})
    run(repo, monkeypatch)  # warms the memo: what is left is the walk
    spawned: list[list[str]] = []
    real = subprocess.run

    def counting(args: list[str], *rest: object, **kwargs: object) -> object:
        if args[0] == "git":
            spawned.append(args)
        return real(args, *rest, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(subprocess, "run", counting)
    assert run(repo, monkeypatch) == 0
    monkeypatch.undo()
    return len(spawned)


def test_an_audits_git_processes_do_not_grow_with_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fresh(name: str) -> Path:
        root = tmp_path / name
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "T")
        git(root, "commit", "-q", "--allow-empty", "-m", "init")
        return root

    short = git_processes_of_an_audit(fresh("short"), monkeypatch, 5)
    long = git_processes_of_an_audit(fresh("long"), monkeypatch, 40)

    assert long == short


@pytest.mark.parametrize(
    "args",
    [["--deadline", "0"], ["--deadline", "-5"], ["--deadline", "1000000000"], ["--budget", "-1"]],
)
def test_seconds_out_of_range_are_a_usage_error(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        audit.main(args)

    assert stopped.value.code == 2
    assert "to 999999999" in capsys.readouterr().err


def test_work_carried_back_to_its_branch_without_a_tree_change_is_judged_where_it_was_done(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    git(repo, "checkout", "-q", "-b", "x")
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})
    git(repo, "checkout", "-q", "feat")  # uncommitted work comes along: no record on feat

    assert run(repo, monkeypatch) == 0
    assert capsys.readouterr().out.startswith("red tests.test_b::test_b ")


def test_a_branch_fast_forwarded_to_observed_work_keeps_its_verdicts(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    git(repo, "checkout", "-q", "-b", "feat2")
    calls.call({"notes.txt": "feat2's own record"})
    git(repo, "checkout", "-q", "feat")
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "b")
    git(repo, "checkout", "-q", "-B", "feat2", "feat")  # the same tree: no record

    assert run(repo, monkeypatch) == 0
    assert capsys.readouterr().out.startswith("red tests.test_b::test_b ")


def test_a_birth_whose_head_commit_is_gone_is_not_judged_alone(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    git(repo, "commit", "-q", "--allow-empty", "-m", "soon amended")
    calls.call({"tests/test_b.py": TEST_B})  # born on that commit
    calls.call({"src/b.py": "B\n"})
    git(repo, "commit", "-q", "--amend", "--allow-empty", "-m", "amended")
    git(repo, "reflog", "expire", "--expire=now", "--all")
    git(repo, "gc", "-q", "--prune=now")  # the birth record's HEAD no longer exists

    assert run(repo, monkeypatch) == 1
    out = capsys.readouterr().out
    assert out.startswith("not-judged tests.test_b::test_b ")
    assert "no longer exists" in out
