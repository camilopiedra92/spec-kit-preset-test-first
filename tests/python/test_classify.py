import ledger

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
