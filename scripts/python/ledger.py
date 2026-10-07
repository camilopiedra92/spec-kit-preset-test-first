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
    return parse_config(raw)


def parse_config(raw: object) -> Config:
    """The configuration a JSON value holds; ConfigError naming what is missing or wrong."""
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


def _snapshot(
    worktree: Path, index: Path, previous: str | None, config: Config
) -> tuple[str, list[str]]:
    """The tree of the worktree's tracked and untracked-but-not-ignored files, as on disk, and
    the paths of a mixed change against the previous record's tree ([] when the change is not
    mixed, or there is no previous record).

    Built in a copy of the worktree's index, in a temporary directory in the system's
    temporary location, so the real index and the worktree are never touched (research R2).
    A copy each call, not an index kept between calls: a kept one goes on tracking what the
    real index stopped tracking, and keeps flags it cleared (research R2, "Kept index").
    """
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
        if previous is None or previous == tree:
            return tree, []
        # One process, pathspec-limited so git skips every directory the globs exclude, read
        # from this call's own index while it exists.
        diff = ["diff-index", "--cached", previous]
        return tree, _mixed(config, _changed(worktree, diff, config.tests + config.sources, env))


def _mixed(config: Config, changed: list[str]) -> list[str]:
    """The changed test and source paths when there are both, else []."""
    tests = _of_kind(config, "test", changed)
    sources = _of_kind(config, "source", changed)
    return tests + sources if tests and sources else []


def _changed(
    worktree: Path, diff: list[str], globs: tuple[str, ...], env: dict[str, str] | None
) -> list[str]:
    """The paths a git diff command lists under the globs' `:(glob)` pathspecs. The pathspecs
    only narrow what git reads: a path's kind is decided by `classify` (a pathspec without a
    wildcard also matches a directory prefix, which a glob does not)."""
    pathspecs = [f":(glob){glob}" for glob in globs]
    listing = git(worktree, *diff, "--no-renames", "--name-only", "-z", "--", *pathspecs, env=env)
    return [path for path in listing.split("\0") if path]


def _of_kind(config: Config, kind: str, paths: list[str]) -> list[str]:
    return [path for path in paths if classify(config, path) == kind]


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
# update-ref's words for a ref that moved since it was read; anything else (a held lock, a full
# disk) is not a race and is reported as it is.
RACE_LOST = ("but expected", "reference already exists")


class Call(TypedDict):
    """Who made the tool call a record follows (the hook input's fields)."""

    session: str
    agent: str | None
    tool: str
    call: str | None


class RecordError(Exception):
    """A record could not be appended."""


class Location(NamedTuple):
    """Where a call ran: the worktree's root and index, and its branch and HEAD commit."""

    root: Path
    index_file: Path
    branch: str | None
    head: str | None


def locate(cwd: Path) -> Location | None:
    """The git worktree of `cwd`, or None outside one -- in one git process in the usual case.

    `--symbolic-full-name` asks git for the branch rather than reading the HEAD file, which
    with the reftable ref format only holds `refs/heads/.invalid`. On an unborn branch HEAD does
    not resolve and the one call fails; that rare case asks again in two.
    """
    asked = ["--path-format=absolute", "--show-toplevel", "--git-path", "index"]
    result = subprocess.run(
        # HEAD before --symbolic-full-name, which applies to every argument after it.
        ["git", "-C", str(cwd), "rev-parse", *asked, "HEAD", "--symbolic-full-name", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        lines = result.stdout.splitlines()
        if len(lines) != 4:
            # rev-parse prints paths unquoted, one per line: a newline in one cannot be parsed.
            raise RecordError(f"cannot record a worktree whose path holds a newline: {cwd!r}")
        root, index, head, symbolic = lines
        branch = (
            symbolic.removeprefix("refs/heads/") if symbolic.startswith("refs/heads/") else None
        )
        return Location(Path(root), Path(index), branch, head)
    unborn = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", *asked], capture_output=True, text=True
    )
    if unborn.returncode != 0:
        return None
    if len(unborn.stdout.splitlines()) != 2:
        raise RecordError(f"cannot record a worktree whose path holds a newline: {cwd!r}")
    root, index = unborn.stdout.splitlines()
    branch = git(Path(root), "symbolic-ref", "--quiet", "--short", "HEAD")
    return Location(Path(root), Path(index), branch, None)


def record(worktree: Path, call: Call, config: Config) -> str | None:
    """Append the worktree's state as a record; None when it equals the newest record's."""
    where = locate(worktree)
    assert where is not None, f"{worktree} is a git worktree"
    return _record(where, call, config)[0]


def _record(where: Location, call: Call, config: Config) -> tuple[str | None, list[str]]:
    """The new record (None when the worktree is unchanged) and the paths of a mixed change it
    made.

    Every git process costs milliseconds on every tool call (SC-003): with `locate`'s one, an
    unchanged worktree takes four -- cat-file for the newest record and its tree, add,
    write-tree -- and a record adds diff-index, commit-tree and update-ref.
    """
    worktree = where.root
    newest, newest_tree = _state(worktree)
    tree, mixed = _snapshot(worktree, where.index_file, newest_tree, config)
    for _ in range(RACE_RETRIES):
        if newest_tree == tree:
            return None, []
        message = _message(call, where.head, where.branch)
        parent = ["-p", newest] if newest else []
        commit = git(worktree, "commit-tree", tree, *parent, "-m", message)
        # Compare-and-swap: moves the ref only if it still points where it was read.
        command = f"update {REF} {commit} {newest}" if newest else f"create {REF} {commit}"
        try:
            git(worktree, "update-ref", "--stdin", input=command + "\n")
        except subprocess.CalledProcessError as error:
            if not any(lost in (error.stderr or "") for lost in RACE_LOST):
                raise RecordError(f"cannot move {REF}: {(error.stderr or '').strip()}") from None
            # Another hook moved the ledger: append on top of its record, and judge this
            # call's change against that record (rare, so the plain tree diff is fine here).
            newest, newest_tree = _state(worktree)
            if newest_tree is not None and newest_tree != tree:
                mixed = _mixed_between(worktree, config, newest_tree, tree)
            continue
        return commit, mixed
    raise RecordError(f"{REF} kept moving: {RACE_RETRIES} attempts lost the race")


def _mixed_between(worktree: Path, config: Config, before: str, after: str) -> list[str]:
    diff = ["diff-tree", "-r", before, after]
    return _mixed(config, _changed(worktree, diff, config.tests + config.sources, None))


def _state(worktree: Path) -> tuple[str | None, str | None]:
    """The newest record and its tree, in one git process; (None, None) before the first."""
    names = f"{REF}\n{REF}^{{tree}}\n"
    lines = git(worktree, "cat-file", "--batch-check=%(objectname)", input=names).splitlines()
    newest, newest_tree = (None if line.endswith(" missing") else line for line in lines)
    return newest, newest_tree


def _message(call: Call, head: str | None, branch: str | None) -> str:
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
    try:
        where = locate(Path(payload["cwd"]))
    except RecordError as error:
        return 2, f"test-first ledger: no record of this call: {error}\n"
    if where is None:
        return 0, ""
    try:
        config = load_config(where.root)
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
        _, changed = _record(where, call, config)
    except subprocess.CalledProcessError as error:
        return 2, f"test-first ledger: no record of this call: {error.stderr or error}\n"
    except (RecordError, OSError) as error:
        # OSError: the temporary index could not be made (a full disk, a read-only $TMPDIR).
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


def main() -> int:
    status, stderr = post_tool_use(json.load(sys.stdin))
    sys.stderr.write(stderr)
    return status
