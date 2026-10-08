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


def test_a_turn_with_a_test_born_green_is_blocked(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"src/b.py": "B\n"})
    calls.call({"tests/test_b.py": TEST_B})

    assert stop(repo, monkeypatch) == 2
    assert "born-green tests.test_b::test_b" in capsys.readouterr().err


def test_a_turn_with_a_test_rewritten_to_green_is_blocked(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"tests/test_b.py": "def test_b(): # expects src/b.py C\n", "src/b.py": "C\n"})

    assert stop(repo, monkeypatch) == 2
    assert "rewritten-to-green tests.test_b::test_b" in capsys.readouterr().err


def test_a_spent_budget_still_judges_from_runs_already_made(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})
    assert stop(repo, monkeypatch) == 2  # makes the runs

    assert stop(repo, monkeypatch, False, "--budget", "0") == 2


def test_the_stop_lists_only_failing_tests_but_counts_every_new_one(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})  # test_b: red
    calls.call({"tests/test_c.py": "def test_c(): # expects src/c.py C\n", "src/c.py": "C\n"})

    assert stop(repo, monkeypatch) == 2
    err = capsys.readouterr().err
    assert "tests.test_b" not in err
    assert err.splitlines()[-1] == "audit: 2 new tests: born-with-code 1, red 1; FAIL"


def test_the_stop_records_the_worktree_under_its_session(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = feature(repo)
    calls.call({"tests/test_b.py": TEST_B})
    (repo / "src" / "b.py").write_text("B\n")  # written outside any recorded call

    stop(repo, monkeypatch)

    message = json.loads(git(repo, "log", "-1", "--format=%B", "refs/worktree/test-first/ledger"))
    assert (message["tool"], message["session"]) == ("Stop", "s")


@pytest.mark.parametrize(
    "where",
    ["detached", "not installed", "no ledger", "not a git worktree"],
)
def test_where_there_is_nothing_to_judge_a_stop_goes_through(
    where: str,
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cwd = repo
    if where == "detached":
        feature(repo).call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})
        git(repo, "checkout", "-q", "--detach")
    elif where == "no ledger":
        feature(repo)
        git(repo, "update-ref", "-d", "refs/worktree/test-first/ledger")
    elif where == "not a git worktree":
        cwd = tmp_path / "plain"
        cwd.mkdir()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cwd": str(cwd), "session_id": "s"})))
    monkeypatch.chdir(cwd)

    assert audit.main(["--stop"]) == 0
    assert capsys.readouterr().err == ""


def test_a_stop_runs_each_replay_under_60_seconds_within_120_in_all(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feature(repo).call({"tests/test_b.py": TEST_B})
    seen: list[tuple[int, int | None]] = []
    real = audit._audit

    def spy(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        seen.append((args[3], args[5]))  # type: ignore[arg-type]
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(audit, "_audit", spy)
    stop(repo, monkeypatch)

    assert seen == [(60, 120)]


@pytest.mark.parametrize("where", ["memo", "temporary directory"])
def test_a_file_system_error_at_a_stop_blocks_with_its_message(
    where: str,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    feature(repo).call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})
    if where == "memo":
        memo = Path(
            git(repo, "rev-parse", "--path-format=absolute", "--git-path", "test-first/runs")
        )
        memo.mkdir(parents=True)
        memo.chmod(0o500)  # read-only: no run can be stored
    else:

        def no_space(*args: object, **kwargs: object) -> str:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr("tempfile.mkdtemp", no_space)

    status = stop(repo, monkeypatch)
    if where == "memo":
        memo.chmod(0o700)

    assert status == 2
    err = capsys.readouterr().err
    assert err.startswith("test-first audit:")
    assert "Traceback" not in err


def test_a_branch_with_no_common_ancestor_blocks_the_stop_with_its_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feature(repo)
    git(repo, "checkout", "-q", "--orphan", "lonely")
    git(repo, "commit", "-q", "-m", "unrelated history")
    Calls(repo).call({"tests/test_b.py": TEST_B})

    assert stop(repo, monkeypatch) == 2
    assert capsys.readouterr().err.startswith("test-first audit:")


def test_the_budget_goes_to_this_turns_files_before_older_ones(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = feature(repo)
    for name in ("a", "b", "c"):  # earlier work, accepted, and alphabetically first
        calls.call({f"tests/test_{name}.py": f"def test_{name}(): # expects src/{name}.py X\n"})
        calls.call({f"src/{name}.py": "X\n"})
    # No earlier Stop: the memo is cold, so the older files cost replays too.
    calls.call({"tests/test_z.py": "def test_z(): # expects src/z.py Z\n", "src/z.py": "Z\n"})
    clock = [0.0]
    replay = audit.Replayer._replay

    def costly(self: audit.Replayer, tree: str, file: str, deadline: int) -> audit.RunResult:
        clock[0] += 10  # each replay takes 10 seconds
        return replay(self, tree, file, deadline)

    monkeypatch.setattr("audit.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(audit.Replayer, "_replay", costly)

    # Judging test_z takes seven replays of the 21 a cold Stop makes: 75 seconds fit it only
    # when it comes first.
    assert stop(repo, monkeypatch, False, "--budget", "75") == 2


def test_a_stop_replays_only_the_files_this_turn_changed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = feature(repo)
    for name in ("a", "b", "c"):
        calls.call({f"tests/test_{name}.py": f"def test_{name}(): # expects src/{name}.py X\n"})
        calls.call({f"src/{name}.py": "X\n"})
    assert stop(repo, monkeypatch) == 0  # an earlier turn's Stop: the memo is warm
    calls.call({"tests/test_z.py": "def test_z(): # expects src/z.py Z\n", "src/z.py": "Z\n"})
    replayed: list[str] = []
    replay = audit.Replayer._replay

    def watched(self: audit.Replayer, tree: str, file: str, deadline: int) -> audit.RunResult:
        replayed.append(file)
        return replay(self, tree, file, deadline)

    monkeypatch.setattr(audit.Replayer, "_replay", watched)

    assert stop(repo, monkeypatch) == 2
    assert set(replayed) == {"tests/test_z.py"}
