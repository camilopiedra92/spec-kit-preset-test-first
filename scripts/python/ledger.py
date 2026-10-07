"""The ledger: a Claude Code PostToolUse hook that records the worktree after every tool call."""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
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
    return any(_wildmatch(glob).fullmatch(path) for glob in globs)


@functools.cache
def _wildmatch(glob: str) -> re.Pattern[str]:
    """git's glob semantics (wildmatch, as in a `:(glob)` pathspec) as a regular expression.

    `*` and `?` stay within a segment; `**/` is zero or more directories; a trailing `/**` is
    everything inside; any other run of asterisks is a plain `*` (research R15).
    """
    out, i = [], 0
    while i < len(glob):
        if glob.startswith("**", i):
            starts_segment = i == 0 or glob[i - 1] == "/"
            if starts_segment and glob.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
                continue
            if starts_segment and i + 2 == len(glob):
                out.append(".*")
                i += 2
                continue
            while i < len(glob) and glob[i] == "*":
                i += 1
            out.append("[^/]*")
            continue
        char = glob[i]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[" and "]" in glob[i + 2 :]:
            end = glob.index("]", i + 2)
            body = glob[i + 1 : end]
            if body.startswith("!"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", "\\\\") + "]")
            i = end
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("".join(out))


def is_mixed(config: Config, paths: list[str]) -> bool:
    """A change is mixed when it holds at least one test path and at least one source path."""
    kinds = {classify(config, path) for path in paths}
    return {"test", "source"} <= kinds


def snapshot(worktree: Path, index: Path | None = None) -> str:
    """The tree of the worktree's tracked and untracked-but-not-ignored files, as on disk."""
    return _snapshot(worktree, index, None, None)[0]


def _snapshot(
    worktree: Path, index: Path | None, previous: str | None, config: Config | None
) -> tuple[str, list[str]]:
    """The worktree's tree and, given the previous record's tree and the configuration, the
    paths of a mixed change against it ([] when the change is not mixed).

    Built in a temporary index seeded from the worktree's own, in the system's temporary
    location, so the real index and the worktree are never touched (research R2). The change
    is read from that index while it exists: `diff-index --cached` limited by `:(glob)`
    pathspecs skips every directory the globs exclude, 7.5 ms on a 1,000-file directory where
    a diff of the two trees cost 20 ms of the hook's 100 (SC-003).
    """
    if index is None:
        index = Path(git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    with tempfile.TemporaryDirectory(prefix="test-first-") as scratch:
        temporary = Path(scratch) / "index"
        if index.exists():
            # copy2 keeps the index's mtime: git rechecks an entry not older than the index
            # file ("racy git"), and a fresh mtime on the copy would let a same-size edit made
            # in the index's last second pass for unchanged (observed: 10 of 10 missed).
            shutil.copy2(index, temporary)
        env = {**os.environ, "GIT_INDEX_FILE": str(temporary)}
        git(worktree, "add", "-A", env=env)
        tree = git(worktree, "write-tree", env=env)
        if previous is None or config is None or previous == tree:
            return tree, []
        tests = _changed(worktree, previous, config.tests, env)
        if not tests:
            return tree, []
        sources = [p for p in _changed(worktree, previous, config.sources, env) if p not in tests]
        return tree, (tests + sources if sources else [])


def _changed(
    worktree: Path, previous: str, globs: tuple[str, ...], env: dict[str, str]
) -> list[str]:
    """The paths matching the globs whose index entry differs from the previous tree."""
    pathspecs = [f":(glob){glob}" for glob in globs]
    listing = git(
        worktree,
        "diff-index",
        "--cached",
        "--no-renames",
        "--name-only",
        "-z",
        previous,
        "--",
        *pathspecs,
        env=env,
    )
    return [path for path in listing.split("\0") if path]


def git(
    worktree: Path, *args: str, env: dict[str, str] | None = None, input: str | None = None
) -> str:
    """git's stdout, stripped; raises CalledProcessError on failure."""
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
    """Append the worktree's state as a record; None when it equals the newest record's."""
    return _record(worktree, call, index, None)[0]


def _record(
    worktree: Path, call: Call, index: Path | None, config: Config | None
) -> tuple[str | None, list[str]]:
    """The new record (None when the worktree is unchanged) and, given the configuration, the
    paths of a mixed change it made.

    Every git process costs milliseconds on every tool call (SC-003): an unchanged worktree
    stops after three -- one cat-file for the newest record, its tree and HEAD, then add and
    write-tree -- and a record adds a pathspec-limited diff-index, commit-tree and update-ref;
    the branch is read from the worktree's HEAD file.
    """
    if index is None:
        index = Path(git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    newest, newest_tree, head = _state(worktree)
    tree, mixed = _snapshot(worktree, index, newest_tree, config)
    for _ in range(RACE_RETRIES):
        if newest_tree == tree:
            return None, []
        message = _message(call, head, _branch(index.parent / "HEAD"))
        parent = ["-p", newest] if newest else []
        commit = git(worktree, "commit-tree", tree, *parent, "-m", message)
        # Compare-and-swap: moves the ref only if it still points where it was read.
        command = f"update {REF} {commit} {newest}" if newest else f"create {REF} {commit}"
        try:
            git(worktree, "update-ref", "--stdin", input=command + "\n")
        except subprocess.CalledProcessError:
            # Another hook moved the ledger: append on top of its record.
            newest, newest_tree, head = _state(worktree)
            continue
        return commit, mixed
    raise RecordError(f"{REF} kept moving: {RACE_RETRIES} attempts lost the race")


def _state(worktree: Path) -> tuple[str | None, str | None, str]:
    """The newest record, its tree, and HEAD's commit, in one git process."""
    names = f"{REF}\n{REF}^{{tree}}\nHEAD\n"
    lines = git(worktree, "cat-file", "--batch-check=%(objectname)", input=names).splitlines()
    newest, newest_tree, head = (None if line.endswith(" missing") else line for line in lines)
    assert head is not None, "HEAD resolves: the installer requires a commit"
    return newest, newest_tree, head


def _branch(head_file: Path) -> str | None:
    """The branch HEAD points at, from the worktree's own HEAD file; None when detached."""
    content = head_file.read_text().strip()
    return (
        content.removeprefix("ref: refs/heads/") if content.startswith("ref: refs/heads/") else None
    )


def _message(call: Call, head: str, branch: str | None) -> str:
    return json.dumps(
        {
            "time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            **call,
            "branch": branch,
            "head": head,
        }
    )


def post_tool_use(payload: dict[str, str]) -> tuple[int, str]:
    """The PostToolUse hook: (exit status, stderr) for one call (contracts/ledger-hook.md)."""
    located = _worktree(Path(payload["cwd"]))
    if located is None:
        return 0, ""
    worktree, index = located
    try:
        config = load_config(worktree)
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
        _, changed = _record(worktree, call, index, config)
    except subprocess.CalledProcessError as error:
        return 2, f"test-first ledger: no record of this call: {error.stderr or error}\n"
    except RecordError as error:
        return 2, f"test-first ledger: no record of this call: {error}\n"
    if changed:
        return 2, mixed_message(config, changed)
    return 0, ""


def mixed_message(config: Config, changed: list[str]) -> str:
    tests = sorted(p for p in changed if classify(config, p) == "test")
    sources = sorted(p for p in changed if classify(config, p) == "source")
    # Worded as a condition: the hook cannot tell a new test from a renamed one without running
    # it, so a rename or a formatter run is told too, and only the audit decides (research R4).
    return (
        "test-first ledger: this call changed tests and code together.\n"
        f"  tests: {', '.join(tests)}\n"
        f"  code:  {', '.join(sources)}\n"
        "If this call added or changed a test together with the code that satisfies it, the\n"
        "audit will fail that test. Redo it while it is cheap: remove the test, revert the code,\n"
        "write the test again in a call that changes no code, run it and see it fail, then\n"
        "restore the code. A rename or a formatter run needs nothing.\n"
    )


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
