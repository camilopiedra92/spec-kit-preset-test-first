from pathlib import Path

import audit
import ledger
from helpers import git
from sequences import snapshot

CONFIG = ledger.Config(tests=("tests/**",), sources=("src/**",), run="x {file} {junit}")


def tree_of(repo: Path, files: dict[str, str]) -> str:
    """A tree holding exactly these files, built without touching the repository's index."""
    for path in git(repo, "ls-files", "--cached", "--others").splitlines():
        (repo / path).unlink(missing_ok=True)
    for path, content in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(content)
    return snapshot(repo)


def contents(repo: Path, tree: str) -> dict[str, str]:
    return {
        path: git(repo, "show", f"{tree}:{path}")
        for path in git(repo, "ls-tree", "-r", "--name-only", tree).splitlines()
    }


def test_the_before_version_takes_tests_from_one_tree_and_the_rest_from_another(
    repo: Path,
) -> None:
    previous = tree_of(
        repo, {"tests/t.py": "old test", "tests/helper.py": "old", "src/a.py": "old"}
    )
    green = tree_of(repo, {"tests/t.py": "new test", "tests/new.py": "n", "src/a.py": "new"})

    tree = audit.compose(repo, CONFIG, tests_from=previous, rest_from=green)

    assert contents(repo, tree) == {
        "tests/t.py": "old test",
        "tests/helper.py": "old",
        "src/a.py": "new",
    }


def test_paths_with_unusual_characters_are_classified_by_their_real_name(repo: Path) -> None:
    old = tree_of(repo, {"tests/año test.py": "old test", "src/naïve.py": "old"})
    new = tree_of(repo, {"tests/año test.py": "new test", "src/naïve.py": "new"})

    tree = audit.compose(repo, CONFIG, tests_from=old, rest_from=new)

    shown = {
        path: git(repo, "cat-file", "-p", f"{tree}:{path}")
        for path in ("tests/año test.py", "src/naïve.py")
    }
    assert shown == {"tests/año test.py": "old test", "src/naïve.py": "new"}


def test_the_base_overlay_keeps_the_bases_code_and_drops_what_the_base_lacks(
    repo: Path,
) -> None:
    base = tree_of(
        repo, {"tests/t.py": "base test", "src/a.py": "base", "templates/x.html": "base"}
    )
    record = tree_of(
        repo,
        {"tests/t.py": "new test", "src/a.py": "new", "src/b.py": "new", "templates/x.html": "new"},
    )

    tree = audit.compose(repo, CONFIG, tests_from=record, rest_from=base)

    assert contents(repo, tree) == {
        "tests/t.py": "new test",
        "src/a.py": "base",
        "templates/x.html": "base",
    }


def test_no_sources_removes_every_source_path_and_keeps_the_rest(repo: Path) -> None:
    record = tree_of(
        repo, {"tests/t.py": "t", "src/a.py": "a", "src/pkg/b.py": "b", "pyproject.toml": "cfg"}
    )

    tree = audit.without_sources(repo, CONFIG, record)

    assert contents(repo, tree) == {"tests/t.py": "t", "pyproject.toml": "cfg"}


def test_the_load_probe_replaces_one_file_and_nothing_else(repo: Path) -> None:
    record = tree_of(repo, {"tests/t.py": "def test(): pass", "tests/u.py": "u", "src/a.py": "a"})

    tree = audit.load_probe(repo, record, "tests/t.py")

    probed = contents(repo, tree)
    assert probed["tests/t.py"] != "def test(): pass"
    assert {path: text for path, text in probed.items() if path != "tests/t.py"} == {
        "tests/u.py": "u",
        "src/a.py": "a",
    }
