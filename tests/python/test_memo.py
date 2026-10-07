import shutil
from pathlib import Path

import audit
import ledger
from helpers import git


def counting(counter: Path, extra: str = "") -> ledger.Config:
    """A run that counts its invocations and reports one passing case."""
    run = (
        f"echo x >> {counter}; {extra}"
        'printf \'<testsuites><testcase classname="c" name="t"/></testsuites>\' > {junit}'
        " # {file}"
    )
    return ledger.Config(tests=("tests/**",), sources=("src/**",), run=run)


def runs(counter: Path) -> int:
    return len(counter.read_text().splitlines()) if counter.exists() else 0


def test_the_same_tree_file_and_command_run_once(repo: Path, tmp_path: Path) -> None:
    counter = tmp_path / "count"
    tree = git(repo, "rev-parse", "HEAD^{tree}")

    with audit.Replayer(repo, counting(counter)) as replayer:
        first = replayer.run(tree, "tests/test_a.py", deadline=30)
        second = replayer.run(tree, "tests/test_a.py", deadline=30)

    assert runs(counter) == 1
    assert second == first


def test_a_different_command_runs_again(repo: Path, tmp_path: Path) -> None:
    counter = tmp_path / "count"
    tree = git(repo, "rev-parse", "HEAD^{tree}")

    with audit.Replayer(repo, counting(counter)) as replayer:
        replayer.run(tree, "tests/test_a.py", deadline=30)
    with audit.Replayer(repo, counting(counter, extra="true; ")) as replayer:
        replayer.run(tree, "tests/test_a.py", deadline=30)

    assert runs(counter) == 2


def test_a_run_that_wrote_no_junit_is_not_kept(repo: Path, tmp_path: Path) -> None:
    counter = tmp_path / "count"
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    broken = ledger.Config(
        tests=("tests/**",), sources=("src/**",), run=f"echo x >> {counter} # {{file}} {{junit}}"
    )

    with audit.Replayer(repo, broken) as replayer:
        assert replayer.run(tree, "tests/test_a.py", deadline=30).outcomes is None
        replayer.run(tree, "tests/test_a.py", deadline=30)

    assert runs(counter) == 2


def test_a_timed_out_run_is_retried_only_under_a_longer_deadline(
    repo: Path, tmp_path: Path
) -> None:
    counter = tmp_path / "count"
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    slow = counting(counter, extra="sleep 3; ")

    with audit.Replayer(repo, slow) as replayer:
        assert replayer.run(tree, "tests/test_a.py", deadline=1).timed_out
        assert replayer.run(tree, "tests/test_a.py", deadline=1).timed_out
        assert runs(counter) == 1
        assert not replayer.run(tree, "tests/test_a.py", deadline=10).timed_out

    assert runs(counter) == 2


def test_a_deleted_memo_gives_the_same_results(repo: Path, tmp_path: Path) -> None:
    counter = tmp_path / "count"
    tree = git(repo, "rev-parse", "HEAD^{tree}")

    with audit.Replayer(repo, counting(counter)) as replayer:
        first = replayer.run(tree, "tests/test_a.py", deadline=30)
        memo = replayer.memo
    shutil.rmtree(memo)
    with audit.Replayer(repo, counting(counter)) as replayer:
        again = replayer.run(tree, "tests/test_a.py", deadline=30)

    assert again == first
    assert runs(counter) == 2


def test_a_memo_entry_that_is_not_json_is_run_again_and_rewritten(
    repo: Path, tmp_path: Path
) -> None:
    counter = tmp_path / "count"
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    config = counting(counter)
    with audit.Replayer(repo, config) as replayer:
        replayer.run(tree, "tests/test_a.py", 30)
    for entry in replayer.memo.iterdir():
        entry.write_text("{truncated")  # corrupted outside the audit

    with audit.Replayer(repo, config) as replayer:
        result = replayer.run(tree, "tests/test_a.py", 30)
        again = replayer.run(tree, "tests/test_a.py", 30)

    assert result.outcomes == {"c::t": "passed"} == again.outcomes
    assert runs(counter) == 2
