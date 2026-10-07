import json
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
