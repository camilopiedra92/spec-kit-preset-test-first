from pathlib import Path

import audit
from helpers import git
from sequences import CONFIG, Calls

TEST_B = "def test_b(): # expects src/b.py B\n"


def report(repo: Path, deadline: int = 30) -> dict[str, audit.Verdict]:
    with audit.Replayer(repo, CONFIG) as replayer:
        return dict(audit.Auditor(repo, CONFIG, replayer, deadline=deadline).report())


def test_only_tests_absent_at_the_base_are_judged(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_a.py": "def test_a(): pass # changed in the feature\n"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})

    assert {test: v.name for test, v in report(repo).items()} == {"tests.test_b::test_b": "red"}


def test_a_test_deleted_before_the_end_is_not_reported(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})
    calls.call({"tests/test_b.py": None})

    assert report(repo) == {}


def test_a_test_file_broken_at_the_newest_record_leaves_its_tests_not_judged(
    repo: Path,
) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})
    calls.call({"tests/test_b.py": "import missing\n" + TEST_B})

    judged = report(repo)

    assert list(judged) == ["tests.test_b::test_b"]
    assert judged["tests.test_b::test_b"].name == "not-judged"
    assert "does not load" in judged["tests.test_b::test_b"].reason


def test_a_command_writing_no_junit_at_the_newest_record_is_named_as_such(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"tests/test_b.py": TEST_B + "# nojunit\n"})

    judged = report(repo)["tests.test_b::test_b"]

    assert (judged.name, "wrote no JUnit" in judged.reason) == ("not-judged", True)


def test_a_test_file_that_does_not_load_at_the_base_leaves_its_tests_not_judged(
    repo: Path,
) -> None:
    (repo / "tests" / "test_b.py").write_text("import missing\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base with a broken test file")
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})

    judged = report(repo)["tests.test_b::test_b"]

    assert (judged.name, "does not load at the base" in judged.reason) == ("not-judged", True)


def test_a_hanging_replay_leaves_its_test_not_judged(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})
    calls.call({"tests/test_b.py": TEST_B + "# hang\n"})

    judged = report(repo, deadline=1)["tests.test_b::test_b"]

    assert (judged.name, "deadline" in judged.reason) == ("not-judged", True)


def test_the_audit_passes_only_on_accepted_and_never_run_verdicts() -> None:
    accepted = [
        ("t::a", audit.Verdict("red")),
        ("t::b", audit.Verdict("predates")),
        ("t::c", audit.Verdict("refactored")),
        ("t::d", audit.Verdict("never-run")),
    ]

    assert audit.exit_status(accepted) == 0
    for failing in (
        "born-with-code",
        "born-green",
        "rewritten-to-green",
        "still-red",
        "unobserved",
        "not-judged",
    ):
        assert audit.exit_status([*accepted, ("t::x", audit.Verdict(failing))]) == 1, failing


def test_a_stash_and_pop_keeps_the_verdict_from_before(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})
    calls.call({"tests/test_b.py": None, "src/b.py": None})  # git stash
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})  # git stash pop

    assert report(repo)["tests.test_b::test_b"].name == "red"


def test_a_file_whose_tests_cannot_be_known_is_itself_not_judged(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B + "# hang\n"})

    judged = report(repo, deadline=1)

    assert list(judged) == ["tests/test_b.py"]
    assert judged["tests/test_b.py"].name == "not-judged"
