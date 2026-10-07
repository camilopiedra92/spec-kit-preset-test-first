"""The ledger: a Claude Code PostToolUse hook that records the worktree after every tool call."""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

CONFIG = Path(".specify") / "test-first.json"


class NotInstalled(Exception):
    """The repository has no configuration: the ledger is not installed there."""


class ConfigError(Exception):
    """The configuration file exists but is not valid."""


@dataclass(frozen=True)
class Config:
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


def snapshot(worktree: Path) -> str:
    """The tree of the worktree's tracked and untracked-but-not-ignored files, as on disk.

    Built in a temporary index seeded from the worktree's own, in the system's temporary
    location, so the real index and the worktree are never touched (research R2).
    """
    index = Path(_git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    with tempfile.TemporaryDirectory(prefix="test-first-") as scratch:
        temporary = Path(scratch) / "index"
        if index.exists():
            shutil.copyfile(index, temporary)
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
RACE_RETRIES = 5


class Call(TypedDict):
    """Who made the tool call a record follows (the hook input's fields)."""

    session: str
    agent: str | None
    tool: str
    call: str | None


class RecordError(Exception):
    """A record could not be appended."""


def record(worktree: Path, call: Call) -> str | None:
    """Append the worktree's state as a record; None when it equals the newest record's."""
    tree = snapshot(worktree)
    message = _message(worktree, call)
    for _ in range(RACE_RETRIES):
        newest = _newest(worktree)
        if newest and _git(worktree, "rev-parse", f"{newest}^{{tree}}") == tree:
            return None
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
    branch = subprocess.run(
        ["git", "-C", str(worktree), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return json.dumps(
        {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            **call,
            "branch": branch or None,
            "head": _git(worktree, "rev-parse", "HEAD"),
        }
    )


def _newest(worktree: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--verify", "--quiet", REF],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None
