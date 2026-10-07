from pathlib import Path

import audit
from helpers import git
from sequences import CONFIG, Calls

B = "tests.test_b::test_b"


def born_at(repo: Path, test: str, file: str) -> int | None:
    """The birth's position among the branch's records (0 is the origin)."""
    with audit.Replayer(repo, CONFIG) as replayer:
        return audit.Auditor(repo, CONFIG, replayer, deadline=30).birth(test, file).at


def test_a_test_in_a_new_file_is_born_where_the_file_was_written(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "def test_b(): # expects src/b.py B\n"})
    calls.call({"src/b.py": "B\n"})

    assert born_at(repo, B, "tests/test_b.py") == 1


def test_a_test_added_to_an_old_file_costs_one_run_beyond_the_touching_ones(
    repo: Path,
) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "def test_old(): pass\n"})
    for n in range(8):
        calls.call({f"src/m{n}.py": "x\n"})
    calls.call({"tests/test_b.py": "def test_old(): pass\ndef test_b(): # expects src/b.py B\n"})

    with audit.Replayer(repo, CONFIG) as replayer:
        born = audit.Auditor(repo, CONFIG, replayer, deadline=30).birth(B, "tests/test_b.py")
        made = len(list(replayer.memo.iterdir()))

    assert born.at == 10
    assert made == 2  # the adding call's run and the one before it


TEST_B = "def test_b(): # expects src/b.py B\n"


def test_a_typo_that_breaks_the_file_for_one_call_is_not_a_new_birth(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"tests/test_b.py": "import missing\n" + TEST_B})
    calls.call({"tests/test_b.py": TEST_B + "# fixed\n"})

    assert born_at(repo, B, "tests/test_b.py") == 1


def test_a_test_first_seen_after_its_file_stopped_failing_to_load_is_born_there(
    repo: Path,
) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "import missing\n" + TEST_B})
    calls.call({"tests/test_b.py": TEST_B})

    assert born_at(repo, B, "tests/test_b.py") == 2


def test_a_file_that_never_loaded_since_the_origin_gives_no_birth(repo: Path) -> None:
    (repo / "tests" / "test_b.py").write_text("import missing\n" + TEST_B)
    calls = Calls(repo)
    calls.call({"README.md": "origin, with the test file already broken"})
    calls.call({"tests/test_b.py": TEST_B})

    assert born_at(repo, B, "tests/test_b.py") is None


def test_a_file_that_loads_once_a_stub_exists_has_its_test_born_at_the_stub(
    repo: Path,
) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": "# needs src/b.py\n" + TEST_B})
    calls.call({"src/b.py": "stub\n"})
    calls.call({"src/b.py": "B\n"})

    assert born_at(repo, B, "tests/test_b.py") == 2


def test_a_test_present_back_to_the_origin_has_no_birth(repo: Path) -> None:
    (repo / "tests" / "test_b.py").write_text(TEST_B)
    (repo / "src" / "b.py").write_text("B\n")
    calls = Calls(repo)
    calls.call({"README.md": "origin, with the test already written"})
    calls.call({"tests/test_b.py": TEST_B + "# edited\n"})

    assert born_at(repo, B, "tests/test_b.py") is None


def test_the_redo_sequence_gives_the_test_a_new_birth_at_its_rewrite(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B, "src/b.py": "B\n"})
    calls.call({"tests/test_b.py": None, "src/b.py": None})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"src/b.py": "B\n"})

    assert born_at(repo, B, "tests/test_b.py") == 3


def birth_of(repo: Path, test: str, file: str) -> audit.Birth:
    with audit.Replayer(repo, CONFIG) as replayer:
        return audit.Auditor(repo, CONFIG, replayer, deadline=30).birth(test, file)


def test_a_test_written_and_committed_in_one_call_is_imported(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B}, commit=True)

    assert birth_of(repo, B, "tests/test_b.py") == audit.Birth(1, imported=True)


def test_a_test_written_then_committed_in_its_own_call_is_not_imported(repo: Path) -> None:
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    calls.call({"tests/test_b.py": TEST_B})
    calls.call({"README.md": "committed"}, commit=True)

    assert birth_of(repo, B, "tests/test_b.py") == audit.Birth(1)


def test_a_test_brought_by_a_merge_is_imported(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat")
    calls = Calls(repo)
    calls.call({"README.md": "origin"})
    git(repo, "checkout", "-q", "-b", "elsewhere", "main")
    (repo / "tests" / "test_b.py").write_text(TEST_B)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "written elsewhere, unseen by this ledger")
    git(repo, "checkout", "-q", "feat")
    git(repo, "merge", "-q", "--no-edit", "elsewhere")
    calls.call({"src/c.py": "after the merge\n"})

    assert birth_of(repo, B, "tests/test_b.py") == audit.Birth(1, imported=True)
