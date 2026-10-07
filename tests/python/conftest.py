from pathlib import Path

import pytest
from helpers import git


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
