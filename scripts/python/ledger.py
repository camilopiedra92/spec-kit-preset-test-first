"""The ledger: a Claude Code PostToolUse hook that records the worktree after every tool call."""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, TypedDict

CONFIG = Path(".specify") / "test-first.json"


class NotInstalled(Exception):
    """The repository has no configuration: the ledger is not installed there."""


class ConfigError(Exception):
    """The configuration file exists but is not valid."""


class Config(NamedTuple):
    tests: tuple[str, ...]
    sources: tuple[str, ...]
    run: str


def load_config(root: Path) -> Config:
    try:
        text = (root / CONFIG).read_text()
    except FileNotFoundError:
        raise NotInstalled(str(root / CONFIG)) from None
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{CONFIG}: {error}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG}: must be a JSON object")
    return Config(tests=_globs(raw, "tests"), sources=_globs(raw, "sources"), run=_run(raw))


def _globs(raw: dict[str, object], field: str) -> tuple[str, ...]:
    value = raw.get(field)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(glob, str) and glob for glob in value)
    ):
        raise ConfigError(f"{CONFIG}: {field} must be a non-empty list of globs")
    return tuple(value)


def _run(raw: dict[str, object]) -> str:
    run = raw.get("run")
    if not isinstance(run, str):
        raise ConfigError(f"{CONFIG}: run must be a command string")
    for placeholder in ("{file}", "{junit}"):
        if placeholder not in run:
            raise ConfigError(f"{CONFIG}: run must contain {placeholder}")
    return run


def classify(config: Config, path: str) -> str:
    """Test, source or other, by the configured globs; a path matching both is a test."""
    if _matches(path, config.tests):
        return "test"
    if _matches(path, config.sources):
        return "source"
    return "other"


def _matches(path: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, glob) for glob in globs)


def is_mixed(config: Config, paths: list[str]) -> bool:
    """A change is mixed when it holds at least one test path and at least one source path."""
    kinds = {classify(config, path) for path in paths}
    return {"test", "source"} <= kinds


def snapshot(worktree: Path, index: Path | None = None) -> str:
    """The tree of the worktree's tracked and untracked-but-not-ignored files, as on disk.

    Built in a temporary index seeded from the worktree's own, in the system's temporary
    location, so the real index and the worktree are never touched (research R2).
    """
    if index is None:
        index = Path(_git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    with tempfile.TemporaryDirectory(prefix="test-first-") as scratch:
        temporary = Path(scratch) / "index"
        if index.exists():
            # copy2 keeps the index's mtime: git rechecks an entry not older than the index
            # file ("racy git"), and a fresh mtime on the copy would let a same-size edit made
            # in the index's last second pass for unchanged (observed: 10 of 10 missed).
            shutil.copy2(index, temporary)
        env = {**os.environ, "GIT_INDEX_FILE": str(temporary)}
        _git(worktree, "add", "-A", env=env)
        return _git(worktree, "write-tree", env=env)


def _git(
    worktree: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None
) -> str:
    return subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        input=input,
    ).stdout.strip()


REF = "refs/worktree/test-first/ledger"
WORKTREE_AND_INDEX = ("--show-toplevel", "--git-path", "index")
RACE_RETRIES = 5


class Call(TypedDict):
    """Who made the tool call a record follows (the hook input's fields)."""

    session: str
    agent: str | None
    tool: str
    call: str | None


class RecordError(Exception):
    """A record could not be appended."""


def record(worktree: Path, call: Call, index: Path | None = None) -> str | None:
    """Append the worktree's state as a record; None when it equals the newest record's.

    Every git process costs milliseconds on every tool call, so the unchanged case -- most
    calls -- stops after five, and a record takes eight (SC-003).
    """
    tree = snapshot(worktree, index)
    message = None
    for _ in range(RACE_RETRIES):
        newest, newest_tree = _newest(worktree)
        if newest_tree == tree:
            return None
        message = message or _message(worktree, call)
        parent = ["-p", newest] if newest else []
        commit = _git(worktree, "commit-tree", tree, *parent, "-m", message)
        # Compare-and-swap: moves the ref only if it still points where it was read.
        command = f"update {REF} {commit} {newest}" if newest else f"create {REF} {commit}"
        try:
            _git(worktree, "update-ref", "--stdin", input=command + "\n")
        except subprocess.CalledProcessError:
            continue
        return commit
    raise RecordError(f"{REF} kept moving: {RACE_RETRIES} attempts lost the race")


def _message(worktree: Path, call: Call) -> str:
    # One process for both: the commit, then the branch's full name, or "HEAD" when detached.
    head, symbolic = _git(worktree, "rev-parse", "HEAD", "--symbolic-full-name", "HEAD").split()
    branch = symbolic.removeprefix("refs/heads/") if symbolic.startswith("refs/heads/") else None
    return json.dumps(
        {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            **call,
            "branch": branch,
            "head": head,
        }
    )


def _newest(worktree: Path) -> tuple[str | None, str | None]:
    """The newest record and its tree, or (None, None) before the first record."""
    result = subprocess.run(
        ["git", "-C", str(worktree), "log", "-1", "--format=%H %T", REF, "--"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None, None
    commit, tree = result.stdout.split()
    return commit, tree


def post_tool_use(payload: dict[str, str]) -> tuple[int, str]:
    """The PostToolUse hook: (exit status, stderr) for one call (contracts/ledger-hook.md)."""
    located = _worktree(Path(payload["cwd"]))
    if located is None:
        return 0, ""
    worktree, index = located
    try:
        load_config(worktree)
    except NotInstalled:
        return 0, ""
    except ConfigError as error:
        return 2, f"test-first ledger: no record of this call: {error}\n"
    call: Call = {
        "session": payload["session_id"],
        "agent": payload.get("agent_id"),
        "tool": payload["tool_name"],
        "call": payload.get("tool_use_id"),
    }
    try:
        record(worktree, call, index)
    except subprocess.CalledProcessError as error:
        return 2, f"test-first ledger: no record of this call: {error.stderr or error}\n"
    except RecordError as error:
        return 2, f"test-first ledger: no record of this call: {error}\n"
    return 0, ""


def _worktree(cwd: Path) -> tuple[Path, Path] | None:
    """The worktree's root and its index file, or None outside a git worktree."""
    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", *WORKTREE_AND_INDEX],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    root, index = result.stdout.splitlines()
    return Path(root), Path(index)


def main() -> int:
    status, stderr = post_tool_use(json.load(sys.stdin))
    sys.stderr.write(stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
