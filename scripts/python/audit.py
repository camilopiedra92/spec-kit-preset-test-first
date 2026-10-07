"""The audit: judges every new test's birth from the ledger, by replaying it (data-model.md)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple
from xml.etree import ElementTree

import ledger

# Installed beside this script as .specify/presets/test-first/scripts/{python,bash}/.
RUNNER = Path(__file__).resolve().parent.parent / "bash" / "run-bounded.sh"
TIMED_OUT = 124  # run-bounded.sh's status when the deadline fired
# A scratch directory names the audit process that owns it, so a later audit can tell one left
# by a killed audit from one a running audit (a Stop hook beside a story close) still uses.
SCRATCH_PREFIX = "test-first-audit-"
SCRATCH_NAME = re.compile(rf"{SCRATCH_PREFIX}(\d+)-.*")


def parse_junit(path: Path) -> dict[str, str] | None:
    """Each test's outcome by id, or None when the run wrote no JUnit (data-model.md, Run)."""
    try:
        root = ElementTree.parse(path).getroot()
    except (FileNotFoundError, ElementTree.ParseError):
        return None
    return {
        f"{case.get('classname', '')}::{case.get('name', '')}": _outcome(case)
        for case in root.iter("testcase")
    }


def _outcome(case: ElementTree.Element) -> str:
    # Any non-pass is a red (research R5): runners do not report an assertion and an exception
    # apart reliably (pytest gives both as <failure>), so failure and error are one outcome.
    children = {child.tag for child in case}
    if children & {"failure", "error"}:
        return "failed"
    if "skipped" in children:
        return "skipped"
    return "passed"


class RunResult(NamedTuple):
    outcomes: dict[str, str] | None
    timed_out: bool


class Observation(NamedTuple):
    outcomes: dict[str, str] | None
    conclusive: bool
    timed_out: bool


class Replayer:
    """Runs one test file at a given tree, in a scratch worktree of its own (research R7).

    The scratch worktree and the JUnit files live in a temporary directory in the system's
    temporary location; the worktree's registration is removed on exit.
    """

    def __init__(self, worktree: Path, config: ledger.Config) -> None:
        self.worktree = worktree
        self.config = config
        self.temporary = Path()
        self.scratch = Path()
        self.memo = Path(
            _git(worktree, "rev-parse", "--path-format=absolute", "--git-path", "test-first/runs")
        )

    def __enter__(self) -> Replayer:
        self._prune_abandoned()
        self.temporary = Path(tempfile.mkdtemp(prefix=f"{SCRATCH_PREFIX}{os.getpid()}-"))
        self.scratch = self.temporary / "worktree"
        _git(
            self.worktree,
            "worktree",
            "add",
            "--quiet",
            "--detach",
            "--no-checkout",
            str(self.scratch),
            "HEAD",
        )
        return self

    def _prune_abandoned(self) -> None:
        """Remove scratch worktrees left registered by audits that were killed."""
        listing = _git(self.worktree, "worktree", "list", "--porcelain")
        for line in listing.splitlines():
            if not line.startswith("worktree "):
                continue
            path = Path(line.removeprefix("worktree "))
            owner = SCRATCH_NAME.fullmatch(path.parent.name)
            if owner and not _alive(int(owner.group(1))):
                _git(self.worktree, "worktree", "remove", "--force", str(path))
                shutil.rmtree(path.parent, ignore_errors=True)

    def __exit__(self, *exc: object) -> None:
        _git(self.worktree, "worktree", "remove", "--force", str(self.scratch))
        shutil.rmtree(self.temporary, ignore_errors=True)

    def run(self, tree: str, file: str, deadline: int) -> RunResult:
        """The file's outcomes at the tree, from the memo when this run was already made."""
        entry = (
            self.memo / hashlib.sha256(f"{tree}\0{file}\0{self.config.run}".encode()).hexdigest()
        )
        if entry.exists():
            stored = json.loads(entry.read_text())
            if not stored["timed_out"] or stored["deadline"] >= deadline:
                return RunResult(stored["outcomes"], stored["timed_out"])
        result = self._replay(tree, file, deadline)
        # A run that wrote no JUnit may be the environment's fault, not the tree's: not kept.
        if result.outcomes is not None or result.timed_out:
            self.memo.mkdir(parents=True, exist_ok=True)
            partial = entry.with_suffix(f".{os.getpid()}.tmp")
            partial.write_text(json.dumps({**result._asdict(), "deadline": deadline}))
            os.replace(partial, entry)  # atomic: a killed audit leaves no torn entry
        return result

    def observe(self, tree: str, file: str, deadline: int) -> Observation:
        """The file's outcomes at the tree, and whether they say which tests exist (R6)."""
        result = self.run(tree, file, deadline)
        outcomes = result.outcomes
        if outcomes is None:
            return Observation(None, conclusive=False, timed_out=result.timed_out)
        if outcomes and all(outcome == "failed" for outcome in outcomes.values()):
            # Every case failed: a load failure looks like this, so compare with the report of
            # the same file made unparseable, on the same tree.
            probe = self.run(load_probe(self.worktree, tree, file), file, deadline)
            if probe.outcomes is not None and set(probe.outcomes) == set(outcomes):
                return Observation(outcomes, conclusive=False, timed_out=False)
        return Observation(outcomes, conclusive=True, timed_out=False)

    def _replay(self, tree: str, file: str, deadline: int) -> RunResult:
        _git(self.scratch, "read-tree", "-u", "--reset", tree)
        _git(self.scratch, "clean", "-fdxq")
        junit = self.temporary / "junit.xml"
        junit.unlink(missing_ok=True)
        command = (
            self.config.run.replace("{file}", shlex.quote(file))
            .replace("{junit}", shlex.quote(str(junit)))
            .replace("{root}", shlex.quote(str(self.worktree)))
        )
        status = subprocess.run(
            ["bash", str(RUNNER), str(deadline), "sh", "-c", command],
            cwd=self.scratch,
            capture_output=True,
        ).returncode
        return RunResult(parse_junit(junit), timed_out=status == TIMED_OUT)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _git(worktree: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(worktree), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def compose(worktree: Path, config: ledger.Config, tests_from: str, rest_from: str) -> str:
    """A tree with exactly the test-side paths of one tree and the other paths of another.

    The replay variants swap whole sides, never only the source globs, so code written outside
    them (a template, a schema) is judged too (research R5, FR-028).
    """
    entries = [entry for entry in _entries(worktree, tests_from) if _is_test(config, entry)] + [
        entry for entry in _entries(worktree, rest_from) if not _is_test(config, entry)
    ]
    return _write_tree(worktree, entries)


def _entries(worktree: Path, tree: str) -> list[str]:
    """`<mode> <type> <object>\t<path>` for every file of the tree, the path unquoted (-z)."""
    listing = _git(worktree, "ls-tree", "-r", "-z", "--full-tree", tree)
    return [entry for entry in listing.split("\0") if entry]


def _is_test(config: ledger.Config, entry: str) -> bool:
    return ledger.classify(config, entry.split("\t", 1)[1]) == "test"


def _write_tree(worktree: Path, entries: list[str]) -> str:
    """The tree of these entries, through a temporary index; the real one is never touched."""
    with tempfile.TemporaryDirectory(prefix="test-first-") as scratch:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        index_info = "".join(
            f"{meta.split()[0]} {meta.split()[2]}\t{path}\0"
            for meta, path in (entry.split("\t", 1) for entry in entries)
        )
        subprocess.run(
            ["git", "-C", str(worktree), "update-index", "-z", "--index-info"],
            input=index_info,
            text=True,
            check=True,
            env=env,
        )
        return subprocess.run(
            ["git", "-C", str(worktree), "write-tree"],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        ).stdout.strip()


def without_sources(worktree: Path, config: ledger.Config, tree: str) -> str:
    """The tree with every source path removed (data-model.md, no-sources)."""
    kept = [
        entry
        for entry in _entries(worktree, tree)
        if ledger.classify(config, entry.split("\t", 1)[1]) != "source"
    ]
    return _write_tree(worktree, kept)


# Content no language parses, as measured on 2026-10-07: pytest 9.1.1 reports it as a
# collection failure and Vitest 5.0.3 as a file that failed to load (research L7).
UNPARSEABLE = "\x01 this is not code {{{ ]]\n"


def load_probe(worktree: Path, tree: str, file: str) -> str:
    """The tree with one file's content replaced by bytes no language parses."""
    garbage = _git_input(worktree, UNPARSEABLE, "hash-object", "-w", "--stdin")
    entries = [
        f"100644 blob {garbage}\t{file}" if entry.split("\t", 1)[1] == file else entry
        for entry in _entries(worktree, tree)
    ]
    return _write_tree(worktree, entries)


def _git_input(worktree: Path, data: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(worktree), *args], input=data, capture_output=True, text=True, check=True
    ).stdout.strip()
