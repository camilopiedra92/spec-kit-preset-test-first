"""The installer: `cli.py install` (contracts/install-ledger.md). One commit holding the project's
configuration and the ledger's two hook entries."""

import argparse
import json
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

import audit
import ledger

SETTINGS = Path(".claude/settings.json")
CLI = '"$CLAUDE_PROJECT_DIR"/.specify/presets/test-first/scripts/python/cli.py'
# Seconds the commit, with the project's commit hooks, gets before its process group is killed:
# the hooks are commands this script does not control (constitution IV).
COMMIT_DEADLINE = 300
MESSAGE = "Record every Claude Code tool call and audit test-first at each stop"
ENTRIES = {
    "PostToolUse": {
        "matcher": "*",
        "hooks": [{"type": "command", "command": f"python3 {CLI} ledger"}],
    },
    # Claude Code cancels a hook at its timeout and discards its output: 300 s holds the Stop
    # audit's worst case (contracts/ledger-hook.md, "Stop").
    "Stop": {
        "hooks": [{"type": "command", "timeout": 300, "command": f"python3 {CLI} audit --stop"}]
    },
}


class Refused(Exception):
    """The installer will not run here; the message says why (exit 1)."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # A usage error is a refusal like any other: exit 1, the repository unchanged.
        raise Refused(message)


def main(argv: list[str]) -> int:
    # Stopped (an agent's command timing out, a hang-up, Ctrl-C or Ctrl-\\): the stop is
    # deferred to a moment no git process holds a lock (_Stop). SIGKILL cannot be caught.
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGQUIT):
        signal.signal(signum, _stop)
    parser = _Parser(prog="cli.py install")
    parser.add_argument("--tests", nargs="+", required=True, help="globs of the test side")
    parser.add_argument("--sources", nargs="+", required=True, help="globs of the code")
    parser.add_argument("--run", required=True, help="runs {file}, writes JUnit XML to {junit}")
    try:
        args = parser.parse_args(argv)
        root = _root(Path.cwd())
        config = {"tests": args.tests, "sources": args.sources, "run": args.run}
        settings = _checked(root, config)
        _stopped_here()  # before the first write: nothing to put back
        _commit(root, {ledger.CONFIG: config, SETTINGS: settings})
        # The ledger's first record: the worktree as the install leaves it, so the first tool
        # call's record is a change and the tests it writes are born in it.
        origin: ledger.Call = {"session": "install", "agent": None, "tool": "install", "call": None}
        try:
            ledger.record(root, origin, ledger.parse_config(config))
        except subprocess.CalledProcessError as error:
            raise ledger.RecordError(f"git failed: {(error.stderr or '').strip()}") from None
        except OSError as error:
            raise ledger.RecordError(str(error)) from None
        _stopped_here()
    except Refused as refusal:
        print(f"test-first install: {refusal}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        # A git failure (a held lock, a full disk) after the checks: the commit's undo has run.
        print(f"test-first install: git failed: {(error.stderr or '').strip()}", file=sys.stderr)
        return 1
    except ledger.RecordError as error:
        print(
            f"test-first install: committed, but the ledger's first record failed: {error}; "
            "the first tool call's record will be the ledger's origin, and the tests it writes "
            "unobserved",
            file=sys.stderr,
        )
        return 1
    return 0


class _Stop:
    """A stop deferred while the install writes. A signal only marks it, and passes SIGTERM to
    the runner of the commit, which can wait on a hook, and is waited for. Raising inside a
    subprocess call would have it SIGKILL git, and even SIGTERM to `git add` left its
    index.lock behind (3 stops in 120), breaking the repository: the short git writes are
    let finish. The stop is acted on between steps (`_stopped_here`), when no git process
    holds a lock."""

    signum: int | None = None
    child: subprocess.Popen[str] | None = None


def _stop(signum: int, frame: object) -> None:
    _Stop.signum = signum
    child = _Stop.child
    if child is not None and child.poll() is None:
        child.terminate()


def _stopped_here() -> None:
    if _Stop.signum is not None:
        raise SystemExit(128 + _Stop.signum)


def _run(argv: list[str]) -> tuple[int, str]:
    """A process a stop passes SIGTERM to, waited for; its status and its output."""
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _Stop.child = child
    if _Stop.signum is not None:
        child.terminate()  # stopped as it started: passed on all the same
    try:
        stdout, stderr = child.communicate()
    finally:
        _Stop.child = None
    return child.returncode, (stderr + stdout).strip()


def _checked(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Every refusal of the contract but the commit's own; the settings with both entries."""
    try:
        parsed = ledger.parse_config(config)
    except ledger.ConfigError as error:
        raise Refused(str(error)) from None
    for glob in parsed.tests + parsed.sources:
        # The hook hands each glob to git as a `:(glob)` pathspec: one git cannot use (outside
        # the repository, magic of its own) would fail every call after this one.
        try:
            ledger.git(root, "ls-files", "--", f":(glob){glob}")
        except subprocess.CalledProcessError as error:
            raise Refused(f"git cannot use {glob} as a path glob: {error.stderr.strip()}") from None
    tracked = ledger.git(root, "ls-files", "-z").split("\0")
    # Matched as the hook and the audit match them (classify), so what is accepted here is
    # what they will see.
    if not any(ledger.classify(parsed, path) == "test" for path in tracked if path):
        raise Refused(f"the test globs {' '.join(parsed.tests)} match no tracked file")
    if not audit.quiet_git(root, "symbolic-ref", "--quiet", "HEAD"):
        raise Refused("HEAD is detached: check out the feature's branch")
    try:
        audit.resolve_base(root)
    except audit.BaseError as error:
        # The audit could never judge this branch: refused now, not at the first stop.
        raise Refused(str(error)) from None
    if subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet"]).returncode != 0:
        raise Refused("something is already staged, and it would land in this commit")
    for path in (SETTINGS, ledger.CONFIG):
        _committable(root, path)
    if not audit.RUNNER.is_file():
        raise Refused(f"{audit.RUNNER} is missing: reinstall the test-first preset")
    settings = _settings(root / SETTINGS)
    hooks = settings.setdefault("hooks", {})
    if _installed(hooks):
        raise Refused(f"{SETTINGS} already has a ledger entry; remove it to install again")
    for event, entry in ENTRIES.items():
        hooks.setdefault(event, []).append(entry)
    return settings


def _commit(root: Path, contents: dict[Path, dict[str, Any]]) -> None:
    """Write each file and commit them, alone, as one commit. Everything was checked before;
    a failure here puts back what was there: the files, their index entries, and a directory
    this run made."""
    written = {path: json.dumps(content, indent=2) for path, content in contents.items()}
    before = {
        path: (root / path).read_bytes() if (root / path).exists() else None for path in written
    }
    made = [] if (root / SETTINGS.parent).exists() else [root / SETTINGS.parent]
    paths = [str(path) for path in written]
    head = audit.quiet_git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    committed = False
    try:
        for directory in made:
            directory.mkdir()
        for path, text in written.items():
            (root / path).write_text(text + "\n")
        _stopped_here()
        # Let finish whatever arrives meanwhile: the stop is acted on just after.
        ledger.git(root, "add", "--", *paths)
        _stopped_here()
        status, output = _run(
            [
                *("bash", str(audit.RUNNER), str(COMMIT_DEADLINE)),
                *("git", "-C", str(root), "commit", "-q", "-m", MESSAGE, "--", *paths),
            ]
        )
        # A post-commit hook runs after git wrote the commit: it stands whatever came after,
        # a failure, the deadline or a stop.
        committed = status == 0 or _landed(root, head, paths)
        if _Stop.signum is not None:
            if committed:
                print(
                    "test-first install: committed before it was stopped, without the ledger's "
                    "first record: the first tool call's record will be its origin, and the "
                    "tests it writes unobserved",
                    file=sys.stderr,
                )
            _stopped_here()
        if status != 0 and committed:
            print(
                f"test-first install: committed; a post-commit hook did not finish or failed: "
                f"{output}",
                file=sys.stderr,
            )
        elif status == audit.TIMED_OUT:
            raise Refused(
                f"the commit did not finish within its {COMMIT_DEADLINE}-second deadline: a "
                "pre-commit or commit-msg hook that hangs"
            )
        elif status != 0:
            raise Refused(f"the commit was refused (a pre-commit or commit-msg hook?): {output}")
    finally:
        if not committed:
            # Not through _run: a stop arriving now must not interrupt the undo.
            subprocess.run(["git", "-C", str(root), "reset", "-q", "--", *paths], check=False)
            for path, content in before.items():
                if content is None:
                    (root / path).unlink(missing_ok=True)
                else:
                    (root / path).write_bytes(content)
            for directory in made:
                directory.rmdir()


def _landed(root: Path, head: str, paths: list[str]) -> bool:
    """Whether this install's commit was written, whatever happened after it: HEAD's parent is
    `head` and HEAD holds, at each path, the blob of what this run wrote there (hashed with the
    path's filters). Not the subject: a prepare-commit-msg hook may rewrite it. Any other move
    of HEAD (a hook or another process committing) is not this install's commit."""
    if audit.quiet_git(root, "log", "-1", "--format=%P", "HEAD") != head:
        return False
    return all(
        audit.quiet_git(root, "rev-parse", "--verify", "--quiet", f"HEAD:{path}")
        == audit.quiet_git(root, "hash-object", "--", path)
        for path in paths
    )


def _settings(path: Path) -> dict[str, Any]:
    """The settings file's object, {} when absent; refused unless its hooks have the shape of
    Claude Code's settings (an object of events, each a list of matcher objects)."""
    if not path.exists():
        return {}
    try:
        settings: object = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise Refused(f"{SETTINGS} is not JSON: {error}") from None
    if not isinstance(settings, dict):
        raise Refused(f"{SETTINGS} is not a JSON object")
    hooks = settings.get("hooks", {})
    if not (
        isinstance(hooks, dict)
        and all(
            isinstance(matchers, list)
            and all(isinstance(m, dict) and _objects(m.get("hooks", [])) for m in matchers)
            for matchers in hooks.values()
        )
    ):
        raise Refused(f"{SETTINGS} is not a settings object with hooks Claude Code can read")
    return settings


def _objects(value: object) -> bool:
    """A list of objects, none with a `command` that is not a string."""
    return isinstance(value, list) and all(
        isinstance(item, dict) and isinstance(item.get("command", ""), str) for item in value
    )


def _installed(hooks: dict[str, Any]) -> bool:
    """Whether any entry of either event already runs this preset's cli.py."""
    return any(
        "test-first/scripts/python/cli.py" in hook.get("command", "")
        for event in ENTRIES
        for matcher in hooks.get(event, [])
        for hook in matcher.get("hooks", [])
    )


def _committable(root: Path, path: Path) -> None:
    """Refuse unless the commit can take `path` whole: absent, or a regular file committed as it
    is on disk, not ignored, and not hidden from git's diff."""
    for parent in reversed(path.parents[:-1]):
        if (root / parent).is_symlink():
            # Written through, the file would land outside the repository.
            raise Refused(f"{parent} is a symlink; {path} needs a directory of its own")
    if (root / path).is_symlink() or ((root / path).exists() and not (root / path).is_file()):
        raise Refused(f"{path} is not a regular file")
    if audit.quiet_git(root, "check-ignore", "--", str(path)):
        raise Refused(f"{path} is ignored by git, so it could not be committed")
    if not (root / path).exists():
        return
    flags = audit.quiet_git(root, "ls-files", "-v", "--", str(path))
    if not flags:
        raise Refused(f"{path} is not committed; commit or remove it first")
    # ls-files -v: lowercase for assume-unchanged, S for skip-worktree; both hide a change from
    # git diff, and the commit would take the file as it is on disk.
    if flags[0].islower() or flags[0] == "S":
        raise Refused(f"{path} is marked skip-worktree or assume-unchanged; clear that first")
    if subprocess.run(["git", "-C", str(root), "diff", "--quiet", "--", str(path)]).returncode:
        raise Refused(f"{path} has uncommitted changes; commit or discard them first")


def _root(cwd: Path) -> Path:
    """`cwd`, when it is the root of a git worktree with Spec Kit installed."""
    top = audit.quiet_git(cwd, "rev-parse", "--show-toplevel")
    if not top or Path(top).resolve() != cwd.resolve() or not (cwd / ".specify").is_dir():
        raise Refused("run it from the root of a git repository with .specify/ in it")
    return cwd
