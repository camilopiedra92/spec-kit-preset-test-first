import time
from pathlib import Path

import audit
import ledger
from helpers import git

# Writes one passing case named after the file and the directory it ran in.
REPORT = (
    'printf \'<testsuites><testsuite><testcase classname="%s" name="%s"/></testsuite>'
    '</testsuites>\' {file} "$(pwd -P)" > {junit}'
)


def config(run: str = REPORT) -> ledger.Config:
    return ledger.Config(tests=("tests/**",), sources=("src/**",), run=run)


def test_a_file_runs_at_a_tree_in_a_scratch_worktree(repo: Path) -> None:
    tree = git(repo, "rev-parse", "HEAD^{tree}")

    with audit.Replayer(repo, config()) as replayer:
        result = replayer.run(tree, "tests/test_a.py", deadline=30)
        scratch = replayer.scratch

    assert result.outcomes == {f"tests/test_a.py::{scratch.resolve()}": "passed"}
    assert not result.timed_out


def test_a_file_name_with_a_space_and_a_quote_reaches_the_command_whole(repo: Path) -> None:
    odd = "tests/it's a test.py"
    (repo / odd).write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "odd name")
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    run = (
        "test -f {file} && "
        'printf \'<testsuites><testcase classname="c" name="ok"/></testsuites>\' > {junit}'
    )

    with audit.Replayer(repo, config(run)) as replayer:
        result = replayer.run(tree, odd, deadline=30)

    assert result.outcomes == {"c::ok": "passed"}


def test_a_hanging_command_is_stopped_at_its_deadline(repo: Path, tmp_path: Path) -> None:
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    marker = tmp_path / "child-alive"
    # A child in the same process group that would outlive a single kill.
    run = f"(while :; do touch {marker}; sleep 0.2; done) & sleep 30 # {{file}} {{junit}}"

    with audit.Replayer(repo, config(run)) as replayer:
        started = time.monotonic()
        result = replayer.run(tree, "tests/test_a.py", deadline=1)
        elapsed = time.monotonic() - started

    assert result == audit.RunResult(None, timed_out=True)
    assert elapsed < 15
    marker.unlink(missing_ok=True)
    time.sleep(1)
    assert not marker.exists(), "a child of the command outlived the deadline"


def test_an_untracked_cache_from_one_run_is_gone_before_the_next(repo: Path) -> None:
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    run = (
        "if [ -e __pycache__/stale.pyc ]; then name=stale; else name=clean; fi; "
        "mkdir -p __pycache__ && touch __pycache__/stale.pyc; "
        'printf \'<testsuites><testcase classname="c" name="%s"/></testsuites>\' $name > {junit}'
        " # {file}"
    )

    with audit.Replayer(repo, config(run)) as replayer:
        replayer.run(tree, "tests/test_a.py", deadline=30)
        second = replayer.run(tree, "tests/test_a.py", deadline=30)

    assert second.outcomes == {"c::clean": "passed"}


def test_root_names_the_real_worktree(repo: Path) -> None:
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    run = (
        'printf \'<testsuites><testcase classname="c" name="%s"/></testsuites>\' {root}'
        " > {junit} # {file}"
    )

    with audit.Replayer(repo, config(run)) as replayer:
        result = replayer.run(tree, "tests/test_a.py", deadline=30)

    assert result.outcomes == {f"c::{repo}": "passed"}


def worktrees(repo: Path) -> list[str]:
    return [
        line.split(" ", 1)[1]
        for line in git(repo, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("worktree ")
    ]


def test_no_scratch_worktree_stays_registered(repo: Path) -> None:
    before = worktrees(repo)

    with audit.Replayer(repo, config()):
        pass

    assert worktrees(repo) == before


def test_a_killed_audits_scratch_worktree_is_pruned_by_the_next(repo: Path, tmp_path: Path) -> None:
    before = worktrees(repo)
    # What a killed audit leaves: its registered scratch worktree, named for a dead process.
    leftover = tmp_path / "test-first-audit-999999-x" / "worktree"
    git(repo, "worktree", "add", "-q", "--detach", str(leftover), "HEAD")

    with audit.Replayer(repo, config()):
        pass

    assert worktrees(repo) == before


def test_a_running_audits_scratch_worktree_is_left_alone(repo: Path, tmp_path: Path) -> None:
    # Process 1 is alive and not ours: another audit that is still running, for this test.
    running = tmp_path / "test-first-audit-1-x" / "worktree"
    git(repo, "worktree", "add", "-q", "--detach", str(running), "HEAD")

    with audit.Replayer(repo, config()):
        pass

    assert str(running.resolve()) in [str(Path(p).resolve()) for p in worktrees(repo)]
