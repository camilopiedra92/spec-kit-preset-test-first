"""The installer: `cli.py install` (contracts/install-ledger.md). One commit holding the project's
configuration and the ledger's two hook entries."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

import audit
import ledger

SETTINGS = Path(".claude/settings.json")
CLI = '"$CLAUDE_PROJECT_DIR"/.specify/presets/test-first/scripts/python/cli.py'
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
    parser = _Parser(prog="cli.py install")
    parser.add_argument("--tests", nargs="+", required=True, help="globs of the test side")
    parser.add_argument("--sources", nargs="+", required=True, help="globs of the code")
    parser.add_argument("--run", required=True, help="runs {file}, writes JUnit XML to {junit}")
    try:
        args = parser.parse_args(argv)
        root = _root(Path.cwd())
        config = {"tests": args.tests, "sources": args.sources, "run": args.run}
        settings = _checked(root, config)
        _commit(root, {ledger.CONFIG: config, SETTINGS: settings})
    except Refused as refusal:
        print(f"test-first install: {refusal}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        # A git failure (a held lock, a full disk) after the checks: the commit's undo has run.
        print(f"test-first install: git failed: {(error.stderr or '').strip()}", file=sys.stderr)
        return 1
    return 0


def _checked(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Every refusal of the contract but the commit's own; the settings with both entries."""
    try:
        parsed = ledger.parse_config(config)
    except ledger.ConfigError as error:
        raise Refused(str(error)) from None
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
    committed = False
    try:
        for directory in made:
            directory.mkdir()
        for path, text in written.items():
            (root / path).write_text(text + "\n")
        ledger.git(root, "add", "--", *paths)
        result = subprocess.run(
            ["git", "-C", str(root), "commit", "-q", "-m", MESSAGE, "--", *paths],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            output = (result.stderr + result.stdout).strip()
            raise Refused(f"the commit was refused (a pre-commit or commit-msg hook?): {output}")
        committed = True
    finally:
        if not committed:
            subprocess.run(["git", "-C", str(root), "reset", "-q", "--", *paths], check=False)
            for path, content in before.items():
                if content is None:
                    (root / path).unlink(missing_ok=True)
                else:
                    (root / path).write_bytes(content)
            for directory in made:
                directory.rmdir()


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
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


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
