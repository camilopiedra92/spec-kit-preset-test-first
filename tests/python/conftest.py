import os
from pathlib import Path

import pytest

from helpers import git


def pytest_configure() -> None:
    """Git as CI sees it: none of the developer's global or system configuration, whose
    core.fsmonitor would start a daemon for every scratch repository, and whose hooks, signing
    or default branch would make a local run differ from CI's."""
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with one commit holding a test and a source file."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "T")
    (root / "tests").mkdir()
    (root / "src").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a(): pass\n")
    (root / "src" / "a.py").write_text("A = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root
