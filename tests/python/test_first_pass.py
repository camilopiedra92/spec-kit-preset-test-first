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


OLD = "tests.test_b::test_old"


def red_then_green_old(repo: Path) -> Calls:
    """test_old written red, then its code: an accepted test of the feature."""
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "def test_old(): # expects src/b.py B\n"})
    calls.call({"src/b.py": "B\n"})
    return calls


def test_a_rename_in_a_test_only_call_is_refactored_listing_the_test_it_replaced(
    repo: Path,
) -> None:
    calls = red_then_green_old(repo)
    record = calls.call({"tests/test_b.py": TEST_B})

    judged = verdict(repo)

    assert (judged.name, judged.record, judged.replaced) == ("refactored", record, (OLD,))


def test_three_accepted_tests_consolidated_are_refactored(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call(
        {
            "tests/test_b.py": "".join(
                f"def test_old{n}(): # expects src/b.py B{n}\n" for n in (1, 2, 3)
            )
        }
    )
    calls.call({"src/b.py": "B1 B2 B3\n"})
    record = calls.call(
        {
            "tests/test_b.py": "".join(
                f"def test_b{n}(): # expects src/b.py B{n}\n" for n in (1, 2, 3)
            )
        }
    )

    judged = verdict(repo, test="tests.test_b::test_b2")

    assert (judged.name, judged.record) == ("refactored", record)
    assert judged.replaced == tuple(f"tests.test_b::test_old{n}" for n in (1, 2, 3))


def test_a_rename_beside_one_more_passing_test_is_no_refactor(repo: Path) -> None:
    calls = red_then_green_old(repo)
    calls.call({"tests/test_b.py": TEST_B + "def test_extra(): # expects src/b.py B\n"})

    assert verdict(repo).name == "born-green"
    assert verdict(repo, test="tests.test_b::test_extra").name == "born-green"


def test_a_rename_with_a_new_case_and_its_code_in_one_call_is_born_with_its_code(
    repo: Path,
) -> None:
    calls = red_then_green_old(repo)
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B and more\n"})

    assert verdict(repo).name == "born-with-code"


def test_an_id_renamed_by_code_alone_is_refactored(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"src/enum.py": "RED\n"})
    calls.call({"tests/test_b.py": "def test_c(): # params src/enum.py src/impl.py\n"})
    calls.call({"src/impl.py": "RED\n"})
    record = calls.call({"src/enum.py": "CRIMSON\n", "src/impl.py": "CRIMSON\n"})

    judged = verdict(repo, test="tests.test_b::test_c[CRIMSON]")

    assert (judged.name, judged.record) == ("refactored", record)
    assert judged.replaced == ("tests.test_b::test_c[RED]",)


def test_behaviour_first_written_in_a_template_outside_sources_is_born_green(
    repo: Path,
) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"templates/page.html": "B\n"})
    calls.call({"tests/test_b.py": "def test_b(): # expects templates/page.html B\n"})

    assert verdict(repo).name == "born-green"
