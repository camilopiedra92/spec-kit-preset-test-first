import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

import audit
import install
import ledger
from helpers import git

RUN = "pytest --junitxml={junit} {file}"
ARGS = ["--tests", "tests/**", "--sources", "src/**", "--run", RUN]


@pytest.fixture
def project(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The repository on a feature branch, with Spec Kit at its root."""
    (repo / ".specify").mkdir()
    (repo / ".specify" / "memory.md").write_text("spec kit\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "spec kit")
    git(repo, "checkout", "-q", "-b", "feat")
    monkeypatch.chdir(repo)
    return repo


def test_an_install_is_one_commit_of_the_configuration_and_both_entries(project: Path) -> None:
    before = git(project, "rev-parse", "HEAD")

    assert install.main(ARGS) == 0

    assert git(project, "rev-parse", "HEAD~1") == before
    assert git(project, "show", "--name-only", "--format=", "HEAD").splitlines() == [
        ".claude/settings.json",
        ".specify/test-first.json",
    ]
    config = json.loads((project / ".specify" / "test-first.json").read_text())
    assert config == {"tests": ["tests/**"], "sources": ["src/**"], "run": RUN}
    hooks = json.loads((project / ".claude" / "settings.json").read_text())["hooks"]
    cli = '"$CLAUDE_PROJECT_DIR"/.specify/presets/test-first/scripts/python/cli.py'
    assert hooks == {
        "PostToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": f"python3 {cli} ledger"}]}
        ],
        "Stop": [
            {
                "hooks": [
                    {"type": "command", "timeout": 300, "command": f"python3 {cli} audit --stop"}
                ]
            }
        ],
    }
    assert git(project, "status", "--porcelain") == ""


GATE = {"hooks": [{"type": "command", "command": "stop-gate.sh", "timeout": 600}]}


def commit_settings(project: Path, settings: dict[str, object]) -> None:
    (project / ".claude").mkdir(exist_ok=True)
    (project / ".claude" / "settings.json").write_text(json.dumps(settings))
    git(project, "add", ".claude/settings.json")
    git(project, "commit", "-q", "-m", "settings")


def test_every_existing_entry_is_kept_and_the_new_ones_added_beside_them(project: Path) -> None:
    commit_settings(project, {"permissions": {"deny": ["Read(./.env)"]}, "hooks": {"Stop": [GATE]}})

    assert install.main(ARGS) == 0

    settings = json.loads((project / ".claude" / "settings.json").read_text())
    assert settings["permissions"] == {"deny": ["Read(./.env)"]}
    assert settings["hooks"]["Stop"][0] == GATE
    assert len(settings["hooks"]["Stop"]) == 2


def state(project: Path) -> tuple[str, ...]:
    """HEAD, the index, and every path's status, ignored ones included."""
    return (
        git(project, "rev-parse", "HEAD"),
        git(project, "ls-files", "--stage"),
        git(project, "status", "--porcelain", "--ignored", "--untracked-files=all"),
    )


def refused(project: Path, capsys: pytest.CaptureFixture[str], argv: list[str] = ARGS) -> str:
    """Install, expecting a refusal that leaves the repository as it was; its message."""
    before = state(project)
    assert install.main(argv) == 1
    assert state(project) == before
    err = capsys.readouterr().err
    assert err.startswith("test-first install: ")
    return err


@pytest.mark.parametrize("where", ["a subdirectory", "a root without .specify"])
def test_outside_the_root_with_spec_kit_it_refuses(
    where: str, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if where == "a subdirectory":
        monkeypatch.chdir(project / "src")
    else:
        git(project, "rm", "-q", "-r", ".specify")
        git(project, "commit", "-q", "-m", "no spec kit")

    assert ".specify" in refused(project, capsys)


@pytest.mark.parametrize(
    ("where", "says"),
    [
        ("detached", "detached"),
        ("on the default branch", "default branch"),
        ("no default branch", "no default branch"),
    ],
)
def test_without_a_feature_branch_and_its_base_it_refuses(
    where: str, says: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if where == "detached":
        git(project, "checkout", "-q", "--detach")
    elif where == "on the default branch":
        git(project, "checkout", "-q", "main")
    else:
        git(project, "branch", "-q", "-m", "main", "trunk")

    assert says in refused(project, capsys)


def test_with_something_staged_it_refuses(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "src" / "a.py").write_text("A = 2\n")
    git(project, "add", "src/a.py")

    assert "staged" in refused(project, capsys)


@pytest.mark.parametrize(
    ("how", "says"),
    [
        ("untracked", "not committed"),
        ("changed", "uncommitted changes"),
        ("ignored", "ignored"),
        ("a directory", "not a regular file"),
        ("a symlink", "not a regular file"),
        ("skip-worktree", "skip-worktree"),
        ("assume-unchanged", "skip-worktree"),
    ],
)
def test_a_settings_file_the_commit_cannot_take_whole_is_refused(
    how: str, says: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = project / ".claude" / "settings.json"
    settings.parent.mkdir()
    if how == "untracked":
        settings.write_text("{}\n")
    elif how == "ignored":
        (project / ".gitignore").write_text(".claude/\n")
        git(project, "add", ".gitignore")
        git(project, "commit", "-q", "-m", "ignore")
        settings.write_text("{}\n")
    elif how == "a directory":
        settings.mkdir()
        (settings / "x").write_text("x\n")
    elif how == "a symlink":
        (project / "elsewhere.json").write_text("{}\n")
        settings.symlink_to(project / "elsewhere.json")
        git(project, "add", "-A")
        git(project, "commit", "-q", "-m", "linked settings")
    else:
        commit_settings(project, {"permissions": {}})
        if how == "changed":
            settings.write_text('{"permissions": {"allow": []}}\n')
        else:
            git(project, "update-index", f"--{how}", ".claude/settings.json")

    assert says in refused(project, capsys)


@pytest.mark.parametrize("event", ["PostToolUse", "Stop"])
def test_with_a_ledger_entry_already_there_it_refuses(
    event: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert install.main(ARGS) == 0
    settings = json.loads((project / ".claude" / "settings.json").read_text())
    kept = {event: settings["hooks"][event]}  # the other entry removed by hand
    commit_settings(project, {"hooks": kept})
    git(project, "rm", "-q", ".specify/test-first.json")
    git(project, "commit", "-q", "-m", "half removed")

    assert "already" in refused(project, capsys)


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (["--tests", "tests/**", "--sources", "src/**", "--run", "pytest {file}"], "{junit}"),
        (["--tests", "tests/**", "--sources", "src/**", "--run", "pytest {junit}"], "{file}"),
        (["--tests", "tests/**", "--sources", "src/**"], "--run"),
        (["--sources", "src/**", "--run", RUN], "--tests"),
        (["--tests", "tests/**", "--run", RUN], "--sources"),
        (["--tests", "", "--sources", "src/**", "--run", RUN], "tests"),
    ],
)
def test_an_incomplete_configuration_is_refused(
    argv: list[str], says: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert says in refused(project, capsys, argv)


@pytest.mark.parametrize("glob", ["spec/**", "tests"])  # the second: a directory is not a glob
def test_test_globs_matching_no_tracked_file_are_refused(
    glob: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "spec").mkdir()
    (project / "spec" / "untracked_test.py").write_text("x\n")
    argv = ["--tests", glob, "--sources", "src/**", "--run", RUN]

    assert "no tracked file" in refused(project, capsys, argv)


@pytest.mark.parametrize("settings", ["absent", "committed"])
def test_a_commit_hook_that_rejects_the_commit_leaves_everything_as_it_was(
    settings: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if settings == "committed":
        commit_settings(project, {"permissions": {}})
    hook = project / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'policy says no' >&2\nexit 1\n")
    hook.chmod(0o755)

    assert "commit" in refused(project, capsys)
    assert (project / ".claude").exists() == (settings == "committed")


@pytest.mark.parametrize(("how", "says"), [("untracked", "not committed"), ("ignored", "ignored")])
def test_a_configuration_file_the_commit_cannot_take_whole_is_refused(
    how: str, says: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = project / ".specify" / "test-first.json"
    if how == "ignored":
        (project / ".gitignore").write_text(".specify/test-first.json\n")
        git(project, "add", ".gitignore")
        git(project, "commit", "-q", "-m", "ignore")
    config.write_text('{"tests": ["x"]}\n')

    assert says in refused(project, capsys)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[]",
        '{"hooks": []}',
        '{"hooks": {"Stop": {}}}',
        '{"hooks": {"Stop": [{"hooks": ["x"]}]}}',
        '{"hooks": {"Stop": ["x"]}}',
        '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": 5}]}]}}',
    ],
)
def test_a_settings_file_that_is_not_a_settings_object_is_refused(
    text: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / ".claude").mkdir()
    (project / ".claude" / "settings.json").write_text(text)
    git(project, "add", ".claude/settings.json")
    git(project, "commit", "-q", "-m", "settings")

    assert "settings.json" in refused(project, capsys)


def test_a_git_error_while_committing_is_a_refusal_that_leaves_everything_as_it_was(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_git = ledger.git

    def locked(
        worktree: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None
    ) -> str:
        if args[0] != "add":
            return real_git(worktree, *args, env=env, input=input)
        (project / ".git" / "index.lock").write_text("")  # another git holds the index
        try:
            return real_git(worktree, *args, env=env, input=input)
        finally:
            (project / ".git" / "index.lock").unlink()

    monkeypatch.setattr(ledger, "git", locked)

    assert "index.lock" in refused(project, capsys)


def test_the_install_starts_the_ledger_at_the_worktree_it_leaves(project: Path) -> None:
    """The first tool call's record must be a change: without an origin before it, the
    tests that call writes would already be in the ledger's first record (unobserved)."""
    assert install.main(ARGS) == 0

    records = git(project, "rev-list", ledger.REF).splitlines()
    assert len(records) == 1
    assert git(project, "rev-parse", f"{ledger.REF}^{{tree}}") == git(
        project, "rev-parse", "HEAD^{tree}"
    )
    assert json.loads(git(project, "log", "-1", "--format=%B", ledger.REF))["tool"] == "install"


@pytest.mark.parametrize("glob", ["/src/**", "../elsewhere/**"])
def test_a_glob_git_cannot_use_as_a_pathspec_is_refused(
    glob: str, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--tests", "tests/**", "--sources", "src/**", glob, "--run", RUN]

    assert glob in refused(project, capsys, argv)


def test_a_symlinked_claude_directory_is_refused_before_anything_is_written(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / ".claude").symlink_to(outside)
    git(project, "add", ".claude")
    git(project, "commit", "-q", "-m", "linked .claude")

    assert "symlink" in refused(project, capsys)
    assert list(outside.iterdir()) == []


def test_an_installer_terminated_during_its_commit_leaves_everything_as_it_was(
    project: Path,
) -> None:
    hook = project / ".git" / "hooks" / "pre-commit"
    started = project.parent / "started"
    hook.write_text(f"#!/bin/sh\ntouch {started}\nsleep 30\n")
    hook.chmod(0o755)
    before = state(project)
    cli = Path(install.__file__).with_name("cli.py")
    proc = subprocess.Popen(
        [sys.executable, str(cli), "install", *ARGS], cwd=project, stderr=subprocess.PIPE
    )
    for _ in range(100):
        if started.exists():
            break
        time.sleep(0.1)
    proc.terminate()
    proc.wait(timeout=10)

    assert state(project) == before


def test_a_first_record_that_fails_after_the_commit_says_what_was_left(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(*args: object) -> None:
        raise ledger.RecordError("disk full")

    monkeypatch.setattr(ledger, "record", failing)

    assert install.main(ARGS) == 1
    err = capsys.readouterr().err
    assert "committed" in err
    assert "first tool call" in err  # what the missing origin means
    assert git(project, "status", "--porcelain") == ""


def test_a_commit_hook_that_outlives_the_deadline_is_refused_with_everything_put_back(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = project / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nsleep 30\n")
    hook.chmod(0o755)
    monkeypatch.setattr(install, "COMMIT_DEADLINE", 2)
    started = time.monotonic()

    assert "deadline" in refused(project, capsys)
    assert time.monotonic() - started < 20


def test_without_the_preset_runner_the_install_refuses_naming_it(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(audit, "RUNNER", project / "missing" / "run-bounded.sh")

    # Refused as a precondition, before any write, not by the commit that needs the runner.
    assert "run-bounded.sh is missing: reinstall the test-first preset" in refused(project, capsys)


def test_a_post_commit_hook_that_outlives_the_deadline_leaves_the_commit_standing(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hook = project / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\nsleep 30\n")  # runs after git has written the commit
    hook.chmod(0o755)
    monkeypatch.setattr(install, "COMMIT_DEADLINE", 2)
    before = git(project, "rev-parse", "HEAD")

    install.main(ARGS)

    assert git(project, "rev-parse", "HEAD~1") == before  # the commit landed
    assert git(project, "status", "--porcelain") == ""  # and nothing was undone under it
    assert "committed" in capsys.readouterr().err


def test_an_installer_terminated_in_a_post_commit_hook_leaves_the_commit_standing(
    project: Path,
) -> None:
    hook = project / ".git" / "hooks" / "post-commit"
    started = project.parent / "started"
    hook.write_text(f"#!/bin/sh\ntouch {started}\nsleep 30\n")
    hook.chmod(0o755)
    before = git(project, "rev-parse", "HEAD")
    cli = Path(install.__file__).with_name("cli.py")
    proc = subprocess.Popen(
        [sys.executable, str(cli), "install", *ARGS], cwd=project, stderr=subprocess.PIPE
    )
    for _ in range(100):
        if started.exists():
            break
        time.sleep(0.1)
    proc.terminate()
    proc.wait(timeout=20)

    assert git(project, "rev-parse", "HEAD~1") == before
    assert git(project, "status", "--porcelain") == ""


@pytest.mark.parametrize("hook_status", [1, 0])
def test_another_commit_moving_head_is_not_taken_for_the_installs(
    hook_status: int, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pre-commit hook that commits something else: refusing (1), or letting git go on to
    lose the race for HEAD (0). Either way the install's own commit did not land."""
    hook = project / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "c=$(git commit-tree HEAD^{tree} -p HEAD -m concurrent) && git update-ref HEAD $c\n"
        f"exit {hook_status}\n"
    )
    hook.chmod(0o755)

    assert install.main(ARGS) == 1
    err = capsys.readouterr().err
    assert "committed" not in err.replace("not committed", "")
    assert git(project, "log", "-1", "--format=%s") == "concurrent"
    assert git(project, "status", "--porcelain") == ""
