from pathlib import Path

import audit
import ledger
from helpers import git
from sequences import CONFIG, LEAKING, Calls

B = "tests.test_b::test_b"
TEST_B = "def test_b(): # expects src/b.py B\n"


def verdict(
    repo: Path, test: str = B, file: str = "tests/test_b.py", config: ledger.Config = CONFIG
) -> audit.Verdict:
    with audit.Replayer(repo, config) as replayer:
        return audit.Auditor(repo, config, replayer, deadline=30).verdict(test, file)


def test_a_test_and_its_code_in_one_call_is_born_with_its_code(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    record = calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})

    judged = verdict(repo)

    assert (judged.name, judged.record) == ("born-with-code", record)


def test_code_first_then_its_test_alone_is_born_green(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"src/b.py": "B\n"})
    record = calls.call({"tests/test_b.py": TEST_B})

    judged = verdict(repo)

    assert (judged.name, judged.record) == ("born-green", record)


def on_feature_with(repo: Path, files: dict[str, str]) -> None:
    """Commit files on main as the base, then work on a feature branch."""
    for name, content in files.items():
        (repo / name).write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "feat")


def test_a_moved_test_that_passes_against_the_base_predates_the_feature(repo: Path) -> None:
    on_feature_with(repo, {"src/b.py": "B\n", "tests/test_old.py": TEST_B})
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    record = calls.call({"tests/test_old.py": None, "tests/test_b.py": TEST_B})

    judged = verdict(repo)

    assert (judged.name, judged.record) == ("predates", record)


def test_a_test_that_passes_without_any_source_is_born_green_with_that_reason(
    repo: Path,
) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "def test_b(): pass\n"})

    judged = verdict(repo)

    assert judged.name == "born-green"
    assert "without any source" in judged.reason


def test_an_environment_using_the_real_worktrees_code_cannot_make_a_test_predate(
    repo: Path,
) -> None:
    on_feature_with(repo, {"src/b.py": "B\n", "tests/test_old.py": TEST_B})
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_old.py": None, "tests/test_b.py": TEST_B})

    judged = verdict(repo, config=LEAKING)

    assert judged.name == "born-green"
    assert "outside the scratch worktree" in judged.reason
