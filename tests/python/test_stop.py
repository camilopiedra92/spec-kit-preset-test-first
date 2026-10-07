import io
import json
from pathlib import Path

import pytest

import audit
from helpers import git
from sequences import CONFIG, Calls

TEST_B = "def test_b(): # expects src/b.py B\n"


def feature(repo: Path) -> Calls:
    (repo / ".specify").mkdir()
    (repo / ".specify" / "test-first.json").write_text(json.dumps(CONFIG._asdict()))
    git(repo, "add", ".specify")
    git(repo, "commit", "-q", "-m", "install")
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    return calls


def stop(repo: Path, monkeypatch: pytest.MonkeyPatch, active: bool = False, *args: str) -> int:
    payload = {"cwd": str(repo), "session_id": "s", "stop_hook_active": active}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.chdir(repo)
    return audit.main(["--stop", *args])


def test_a_turn_with_a_test_born_with_its_code_is_blocked_naming_it(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    record = calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})

    assert stop(repo, monkeypatch) == 2
    err = capsys.readouterr().err
    assert f"born-with-code tests.test_b::test_b {record} Bash c2" in err


def test_a_stop_already_continued_by_a_stop_hook_goes_through(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})

    assert stop(repo, monkeypatch, True) == 0


def test_a_turn_ending_on_the_red_case_in_progress_goes_through(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})

    assert stop(repo, monkeypatch) == 0
    assert capsys.readouterr().err == ""


def test_verdicts_a_later_call_can_change_do_not_block(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "tests" / "test_old.py").write_text("def test_pre(): pass\n")  # before the ledger
    calls = feature(repo)
    calls.call({"tests/test_s.py": "def test_s(): # skip\n"})  # never run

    assert stop(repo, monkeypatch) == 0


def test_a_malformed_configuration_blocks_with_its_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feature(repo)
    (repo / ".specify" / "test-first.json").write_text('{"tests": []}')

    assert stop(repo, monkeypatch) == 2
    assert "tests" in capsys.readouterr().err


def test_on_the_default_branch_a_stop_goes_through(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature(repo)
    git(repo, "checkout", "-q", "-B", "main", "feat")

    assert stop(repo, monkeypatch) == 0


def memo_entries(repo: Path) -> int:
    memo = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "test-first/runs"))
    return len(list(memo.iterdir())) if memo.exists() else 0


def test_a_spent_budget_starts_no_replay_and_lets_the_stop_through(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})

    assert stop(repo, monkeypatch, False, "--budget", "0") == 0
    assert capsys.readouterr().err == ""
    assert memo_entries(repo) == 0


def test_the_next_turn_reuses_the_runs_already_made(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})
    assert stop(repo, monkeypatch) == 2
    made = memo_entries(repo)

    assert stop(repo, monkeypatch) == 2
    assert memo_entries(repo) == made


def test_no_base_that_resolves_blocks_with_its_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    git(repo, "branch", "-m", "main", "trunk")

    assert stop(repo, monkeypatch) == 2
    assert "tried" in capsys.readouterr().err


def lock_the_ledger(repo: Path) -> None:
    lock = Path(
        git(
            repo,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "refs/worktree/test-first/ledger.lock",
        )
    )
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("held\n")


def test_a_git_error_at_a_stop_blocks_with_its_message(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    lock_the_ledger(repo)
    (repo / "src" / "b.py").write_text("B\n")  # dirty: the Stop must record it

    assert stop(repo, monkeypatch) == 2
    err = capsys.readouterr().err
    assert "test-first audit:" in err
    assert "Traceback" not in err
