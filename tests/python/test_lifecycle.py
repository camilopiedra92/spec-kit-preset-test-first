from pathlib import Path

import pytest

import audit
from sequences import CONFIG, Calls

B = "tests.test_b::test_b"
TEST_B = "def test_b(): # expects src/b.py B\n"


def follow(repo: Path) -> audit.Lifecycle:
    with audit.Replayer(repo, CONFIG) as replayer:
        auditor = audit.Auditor(repo, CONFIG, replayer, deadline=30)
        birth = auditor.birth(B, "tests/test_b.py")
        assert birth.at is not None
        return auditor.follow(B, "tests/test_b.py", birth.at)


def test_red_at_birth_then_green_by_code_alone_is_red(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})

    assert follow(repo) == audit.Lifecycle("red", at=2)


def test_a_red_test_changed_in_the_call_that_turns_it_green_is_rewritten(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"tests/test_b.py": "def test_b(): # expects src/b.py C\n", "src/b.py": "C\n"})

    assert follow(repo) == audit.Lifecycle("rewritten-to-green", at=2)


def test_a_red_test_turned_green_by_a_helper_alone_is_rewritten(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call(
        {
            "tests/helper.py": "value = 'beta'\n",
            "tests/test_b.py": "def test_b(): # expects tests/helper.py alpha\n",
        }
    )
    calls.call({"tests/helper.py": "value = 'alpha'\n"})

    assert follow(repo) == audit.Lifecycle("rewritten-to-green", at=2)


def test_an_api_changed_with_its_shared_fixture_in_one_call_is_not_judged(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call(
        {
            "src/v1.py": "api\n",
            "tests/fixture.py": "# needs src/v1.py\n",
            "tests/test_b.py": "# uses tests/fixture.py\n" + TEST_B,
        }
    )
    calls.call(
        {
            "src/v1.py": None,
            "src/v2.py": "api\n",
            "tests/fixture.py": "# needs src/v2.py\n",
            "src/b.py": "B\n",
        }
    )

    lifecycle = follow(repo)

    assert (lifecycle.state, lifecycle.at) == ("not-judged", 2)
    assert "shared test support" in lifecycle.reason


def test_skipped_at_birth_then_red_then_green_is_red(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "def test_b(): # skip\n"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})

    assert follow(repo) == audit.Lifecycle("red", at=3)


def test_still_failing_at_the_newest_record_is_still_red(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})

    assert follow(repo) == audit.Lifecycle("still-red", at=None)


def test_only_ever_skipped_is_never_run(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "def test_b(): # skip\n"})

    assert follow(repo) == audit.Lifecycle("never-run", at=None)


def test_a_replay_past_its_deadline_is_not_judged(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"tests/test_b.py": TEST_B + "# hang\n"})

    with audit.Replayer(repo, CONFIG) as replayer:
        auditor = audit.Auditor(repo, CONFIG, replayer, deadline=1)
        with pytest.raises(audit.NotJudged, match="deadline"):
            auditor.follow(B, "tests/test_b.py", 1)


def test_a_red_test_edited_until_it_passes_in_a_test_only_call_is_rewritten(
    repo: Path,
) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"src/b.py": "A\n"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"tests/test_b.py": "def test_b(): # expects src/b.py A\n"})

    assert follow(repo) == audit.Lifecycle("rewritten-to-green", at=3)
