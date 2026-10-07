from pathlib import Path

import ledger
from helpers import git

CONFIG = ledger.Config(tests=("tests/**",), sources=("src/**",), run="x {file} {junit}")


def test_a_path_matching_tests_is_a_test() -> None:
    assert ledger.classify(CONFIG, "tests/a.py") == "test"


def test_double_star_crosses_directories() -> None:
    assert ledger.classify(CONFIG, "tests/a/b/c.py") == "test"


def test_a_path_matching_sources_is_a_source() -> None:
    assert ledger.classify(CONFIG, "src/x.py") == "source"


def test_a_path_matching_both_lists_is_a_test() -> None:
    both = ledger.Config(tests=("**/test_*.py",), sources=("pkg/**",), run="x {file} {junit}")

    assert ledger.classify(both, "pkg/test_a.py") == "test"


def test_documentation_and_tasks_are_other() -> None:
    assert ledger.classify(CONFIG, "README.md") == "other"
    assert ledger.classify(CONFIG, "specs/001/tasks.md") == "other"


def test_a_change_of_a_test_and_a_source_is_mixed() -> None:
    assert ledger.is_mixed(CONFIG, ["tests/t.py", "src/x.py"])


def test_tests_and_other_paths_alone_are_not_mixed() -> None:
    assert not ledger.is_mixed(CONFIG, ["tests/t.py", "README.md"])
    assert not ledger.is_mixed(CONFIG, ["src/x.py", "README.md"])


ANYWHERE = ledger.Config(tests=("**/test_*.py",), sources=("src/*.py",), run="x {file} {junit}")


def test_double_star_slash_matches_zero_directories() -> None:
    assert ledger.classify(ANYWHERE, "test_x.py") == "test"
    assert ledger.classify(ANYWHERE, "a/b/test_x.py") == "test"


def test_a_single_star_stays_within_a_directory() -> None:
    assert ledger.classify(ANYWHERE, "src/a.py") == "source"
    assert ledger.classify(ANYWHERE, "src/a/b.py") == "other"


GLOBS = [
    "tests/**",
    "**/test_*.py",
    "src/*.py",
    "src/**/*.py",
    "**/*.test.[jt]s",
    "lib/?.py",
    "a/**/b",
    "docs/*",
    "x**y.py",
]
PATHS = [
    "test_x.py",
    "tests/a.py",
    "tests/a/b/c.py",
    "c/d/test_x.py",
    "src/a.py",
    "src/a/b.py",
    "src/a/b/c.py",
    "web/x.test.ts",
    "x.test.js",
    "x.test.cs",
    "lib/a.py",
    "lib/ab.py",
    "a/b",
    "a/x/y/b",
    "docs/d/e.md",
    "xaby.py",
    "x/y.py",
]


def test_every_glob_matches_exactly_what_git_matches(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    for path in PATHS:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x\n")
    git(tmp_path, "add", "-A")
    for glob in GLOBS:
        by_git = set(git(tmp_path, "ls-files", f":(glob){glob}").splitlines())
        config = ledger.Config(tests=(glob,), sources=("nothing",), run="x {file} {junit}")
        ours = {path for path in PATHS if ledger.classify(config, path) == "test"}
        assert ours == by_git, glob
