"""The audit: judges every new test's birth from the ledger, by replaying it (data-model.md)."""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple
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

    def __init__(self, worktree: Path, config: ledger.Config, budget: int | None = None) -> None:
        self.worktree = worktree
        self.config = config
        # A Stop audit starts no replay after its budget; memoized runs cost nothing and go on.
        self.spent_at = time.monotonic() + budget if budget is not None else None
        self.temporary = Path()
        self.scratch = Path()
        self.memo = Path(
            ledger.git(
                worktree, "rev-parse", "--path-format=absolute", "--git-path", "test-first/runs"
            )
        )

    def __enter__(self) -> Replayer:
        self._prune_abandoned()
        self.temporary = Path(tempfile.mkdtemp(prefix=f"{SCRATCH_PREFIX}{os.getpid()}-"))
        self.scratch = self.temporary / "worktree"
        ledger.git(
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
        listing = ledger.git(self.worktree, "worktree", "list", "--porcelain")
        for line in listing.splitlines():
            if not line.startswith("worktree "):
                continue
            path = Path(line.removeprefix("worktree "))
            owner = SCRATCH_NAME.fullmatch(path.parent.name)
            if owner and not _alive(int(owner.group(1))):
                ledger.git(self.worktree, "worktree", "remove", "--force", str(path))
                shutil.rmtree(path.parent, ignore_errors=True)

    def __exit__(self, *exc: object) -> None:
        ledger.git(self.worktree, "worktree", "remove", "--force", str(self.scratch))
        shutil.rmtree(self.temporary, ignore_errors=True)

    def run(self, tree: str, file: str, deadline: int) -> RunResult:
        """The file's outcomes at the tree, from the memo when this run was already made."""
        entry = (
            self.memo / hashlib.sha256(f"{tree}\0{file}\0{self.config.run}".encode()).hexdigest()
        )
        stored = _stored(entry)
        if stored is not None and (not stored["timed_out"] or stored["deadline"] >= deadline):
            return RunResult(stored["outcomes"], stored["timed_out"])
        if self.spent_at is not None and time.monotonic() >= self.spent_at:
            raise BudgetSpent("the Stop hook's budget ran out before this replay")
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
            if probe.timed_out:
                # Whether the file loaded cannot be told: the judgement waits on a longer run.
                return Observation(outcomes, conclusive=False, timed_out=True)
            if probe.outcomes is not None and set(probe.outcomes) == set(outcomes):
                return Observation(outcomes, conclusive=False, timed_out=False)
        return Observation(outcomes, conclusive=True, timed_out=False)

    def _replay(self, tree: str, file: str, deadline: int) -> RunResult:
        ledger.git(self.scratch, "read-tree", "-u", "--reset", tree)
        ledger.git(self.scratch, "clean", "-fdxq")
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


def _stored(entry: Path) -> dict[str, Any] | None:
    """A memo entry, or None when there is none or it cannot be read: entries are written
    atomically, so only something outside the audit corrupts one, and the run is made again."""
    try:
        stored = json.loads(entry.read_text())
    except (FileNotFoundError, ValueError):
        return None
    if not isinstance(stored, dict) or not {"outcomes", "timed_out", "deadline"} <= stored.keys():
        return None
    return stored


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def compose(worktree: Path, config: ledger.Config, tests_from: str, rest_from: str) -> str:
    """A tree with exactly the test-side paths of one tree and the other paths of another.

    The replay variants swap whole sides, never only the source globs, so code written outside
    them (a template, a schema) is judged too (research R5, FR-028).
    """
    tests = [e for e in _entries(worktree, tests_from) if _kind(config, e) == "test"]
    rest = [e for e in _entries(worktree, rest_from) if _kind(config, e) != "test"]
    return _write_tree(worktree, tests + rest)


class Entry(NamedTuple):
    """One file of a tree: its mode, its blob, its path."""

    mode: str
    blob: str
    path: str


def _entries(worktree: Path, tree: str) -> list[Entry]:
    """Every file of the tree, the path unquoted (-z)."""
    listing = ledger.git(worktree, "ls-tree", "-r", "-z", "--full-tree", tree)
    entries = []
    for line in filter(None, listing.split("\0")):
        meta, path = line.split("\t", 1)
        mode, _, blob = meta.split()
        entries.append(Entry(mode, blob, path))
    return entries


def _kind(config: ledger.Config, entry: Entry) -> str:
    return ledger.classify(config, entry.path)


def _write_tree(worktree: Path, entries: list[Entry]) -> str:
    """The tree of these entries, through a temporary index; the real one is never touched."""
    with tempfile.TemporaryDirectory(prefix="test-first-") as scratch:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
        index_info = "".join(f"{e.mode} {e.blob}\t{e.path}\0" for e in entries)
        ledger.git(worktree, "update-index", "-z", "--index-info", env=env, input=index_info)
        return ledger.git(worktree, "write-tree", env=env)


def without_sources(worktree: Path, config: ledger.Config, tree: str) -> str:
    """The tree with every source path removed (data-model.md, no-sources)."""
    kept = [e for e in _entries(worktree, tree) if _kind(config, e) != "source"]
    return _write_tree(worktree, kept)


# Content no language parses, as measured on 2026-10-07: pytest 9.1.1 reports it as a
# collection failure and Vitest 5.0.3 as a file that failed to load (research L7).
UNPARSEABLE = "\x01 this is not code {{{ ]]\n"


def load_probe(worktree: Path, tree: str, file: str) -> str:
    """The tree with one file's content replaced by bytes no language parses."""
    garbage = ledger.git(worktree, "hash-object", "-w", "--stdin", input=UNPARSEABLE)
    entries = [
        Entry("100644", garbage, file) if entry.path == file else entry
        for entry in _entries(worktree, tree)
    ]
    return _write_tree(worktree, entries)


class BaseError(Exception):
    """No base to judge new tests against."""

    def __init__(self, message: str, on_default_branch: bool = False) -> None:
        super().__init__(message)
        self.on_default_branch = on_default_branch


def resolve_base(worktree: Path, override: str | None = None) -> str:
    """The commit new tests are new against (data-model.md, Base)."""
    if override is not None:
        given = quiet_git(worktree, "rev-parse", "--verify", "--quiet", f"{override}^{{commit}}")
        if not given:
            raise BaseError(f"--base {override} names no commit")
        return given
    if "origin" in quiet_git(worktree, "remote").split():
        # Remote-tracking first: a local merge into the default branch cannot move these.
        named = quiet_git(worktree, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
        candidates = [named.removeprefix("refs/remotes/"), "origin/main", "origin/master"]
    else:
        configured = quiet_git(worktree, "config", "init.defaultBranch")
        candidates = [configured, "main", "master"]
    tried = [ref for ref in candidates if ref]
    default = next(
        (ref for ref in tried if quiet_git(worktree, "rev-parse", "--verify", "--quiet", ref)),
        None,
    )
    if default is None:
        raise BaseError(f"no default branch to take the base from: tried {', '.join(tried)}")
    branch = quiet_git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch == default.removeprefix("origin/"):
        raise BaseError(
            f"HEAD is on the default branch, {branch}: nothing is new against it",
            on_default_branch=True,
        )
    fork = quiet_git(worktree, "merge-base", "HEAD", default)
    if not fork:
        raise BaseError(f"HEAD shares no history with {default}: nothing is new against it")
    return fork


def quiet_git(worktree: Path, *args: str) -> str:
    """git's output, or "" when the command fails (an absent ref, for instance)."""
    result = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


class Record(NamedTuple):
    commit: str
    tree: str
    branch: str | None
    head: str | None
    tool: str = ""
    call: str | None = None


def effective_history(records: list[Record]) -> list[Record]:
    """The records of the current line of work, oldest first (data-model.md).

    The ledger's newest record is where the worktree stands now: the audit records it first, so
    a current branch that the newest record does not name was created or checked out without
    changing the tree, which adds no record (FR-002), and its work is the newest record's line.
    Walking back from it with that record's branch as the lineage: a record on the lineage is
    included; one off it is skipped when the lineage has an older record (a visit elsewhere and
    back), and otherwise included as the line the lineage came from.
    """
    if not records:
        return []
    first: dict[str | None, int] = {}
    for i, record in enumerate(records):
        first.setdefault(record.branch, i)
    lineage = records[-1].branch
    line = [records[-1]]
    for i in range(len(records) - 2, -1, -1):
        record = records[i]
        if record.branch != lineage:
            if first.get(lineage, i) < i:
                continue
            lineage = record.branch
        line.append(record)
    return line[::-1]


def load_records(worktree: Path) -> list[Record]:
    """The worktree's ledger, oldest record first; empty when there is none."""
    log = quiet_git(worktree, "log", "--reverse", "-z", "--format=%H %T %B", ledger.REF, "--")
    records = []
    for entry in filter(None, log.split("\0")):
        commit, tree, message = entry.split(" ", 2)
        fields = json.loads(message)
        records.append(
            Record(commit, tree, fields["branch"], fields["head"], fields["tool"], fields["call"])
        )
    return records


def changed_paths_of(worktree: Path, pairs: list[tuple[str, str]]) -> list[set[str]]:
    """The change of each pair of trees -- the paths whose presence or content differs
    (data-model.md, Change) -- from one git process whatever their number: the walk of a long
    ledger would otherwise cost a process per record on every audit.

    `diff-tree --stdin` echoes each input line, then that pair's paths, NUL-terminated; the
    next echo is known, since it is the next pair, so a path can never be taken for one.
    """
    if not pairs:
        return []
    lines = "".join(f"{before} {after}\n" for before, after in pairs)
    # Not ledger.git: its strip would take the newline that ends an empty last pair's echo.
    out = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "diff-tree",
            "--stdin",
            "-r",
            "-z",
            "--no-renames",
            "--name-only",
        ],
        check=True,
        capture_output=True,
        text=True,
        input=lines,
    ).stdout
    changes: list[set[str]] = []
    at = 0
    for k, (before, after) in enumerate(pairs):
        header = f"{before} {after}\n"
        assert out.startswith(header, at), f"diff-tree --stdin echoed no {header!r}"
        at += len(header)
        following = f"{pairs[k + 1][0]} {pairs[k + 1][1]}\n" if k + 1 < len(pairs) else None
        paths: set[str] = set()
        while at < len(out) and not (following and out.startswith(following, at)):
            end = out.index("\0", at)
            paths.add(out[at:end])
            at = end + 1
        changes.append(paths)
    return changes


class Birth(NamedTuple):
    at: int | None
    imported: bool = False


class NotJudged(Exception):
    """A run the judgement depends on could not be made; the reason says why."""


class BudgetSpent(NotJudged):
    """A Stop audit's budget ran out: judged by a later turn or the story-close audit."""


class Lifecycle(NamedTuple):
    """Where a test's life from its birth ended: its state, the record, and why."""

    state: str
    at: int | None
    reason: str = ""


# Verdicts that do not fail the audit and can stand for a test that replaces them.
ACCEPTED = frozenset({"red", "predates", "refactored"})


class Verdict(NamedTuple):
    """An audit's judgement of one test: its kind, the record it rests on, and why."""

    kind: str
    record: str | None = None
    reason: str = ""
    replaced: tuple[str, ...] = ()


class Auditor:
    """Judges tests along the current branch's effective history (data-model.md)."""

    def __init__(
        self,
        worktree: Path,
        config: ledger.Config,
        replayer: Replayer,
        deadline: int,
        base: str | None = None,
    ) -> None:
        self.worktree = worktree
        self.config = config
        self.replayer = replayer
        self.deadline = deadline
        self.base_override = base
        self._base_tree: str | None = None
        # Keyed by the two trees, so an auditor limited to an earlier history (until) shares it.
        self._changes: dict[tuple[str, str], set[str]] = {}
        self.history = effective_history(load_records(worktree))

    def birth(self, test: str, file: str) -> Birth:
        """Where the test last appeared after being absent (data-model.md, Finding a birth).

        Walks back over the records that changed the test's file: one run there and one before
        decide most births. A test that appeared without its file changing (its file started to
        load, or its id comes from code or data) is found by a scan forward from where it was
        last seen absent.
        """
        touching = [i for i in range(1, len(self.history)) if file in self.change(i)]
        for t in reversed(touching):
            at_t = self.observe(t, file)
            if not at_t.conclusive:
                continue  # a typo for a call says nothing either way
            if test not in (at_t.outcomes or {}):
                return self.scan(test, file, t)
            j = self.conclusive_before(t, file)
            if j is None:
                # Unknown since the origin: the test may predate the ledger. Fail closed.
                return Birth(None)
            if test not in (self.observe(j, file).outcomes or {}):
                return self.born(test, file, t)
            # Reported at j as well: the touching records between are inconclusive, so the
            # walk goes on from the next one older than j.
        # No touching record decided it: look before the oldest one (the origin when the file
        # never changed). The file there is as at the origin, but the rest of the tree may have
        # made it load.
        before = self.conclusive_before(touching[0], file) if touching else 0
        if before is None or not self.observe(before, file).conclusive:
            return Birth(None)
        if test not in (self.observe(before, file).outcomes or {}):
            return self.scan(test, file, before)
        return Birth(None)  # reported back to where its file was last unchanged: no birth seen

    def scan(self, test: str, file: str, absent_at: int) -> Birth:
        """The first record after `absent_at` whose conclusive run reports the test."""
        for k in range(absent_at + 1, len(self.history)):
            seen = self.observe(k, file)
            if seen.conclusive and test in (seen.outcomes or {}):
                return self.born(test, file, k)
        return Birth(None)

    def born(self, test: str, file: str, b: int) -> Birth:
        """A birth at record b, imported when it came with commits this ledger did not see
        written: b's HEAD moved and the new HEAD's own tree already holds the test."""
        record, previous = self.history[b], self.history[b - 1]
        if record.head is not None and record.head != previous.head:
            committed = ledger.git(self.worktree, "rev-parse", f"{record.head}^{{tree}}")
            seen = self.observe_tree(committed, file)
            if test in (seen.outcomes or {}):
                return Birth(b, imported=True)
        return Birth(b)

    def report(self) -> list[tuple[str, Verdict]]:
        """Every new test with its verdict (data-model.md, Verdict): reported at the newest
        record by a test-side file that differs from the base, and not by the base's run."""
        newest = self.history[-1].tree
        files = sorted(
            path
            for path in changed_paths_of(self.worktree, [(self.base_tree(), newest)])[0]
            if ledger.classify(self.config, path) == "test"
        )
        judged: list[tuple[str, Verdict]] = []
        for file in files:
            judged.extend(self.report_file(file))
        return judged

    def report_file(self, file: str) -> list[tuple[str, Verdict]]:
        """The new tests of one file with their verdicts."""
        held, unjudged = self.held_tests(file)
        if held is None:
            # No run says which tests the file holds: the file itself stands unjudged, so an
            # audit that cannot see a file's tests cannot pass for lack of them.
            return [(file, Verdict("not-judged", reason=unjudged))]
        try:
            at_base = self.observe_tree(self.base_tree(), file)
        except NotJudged as error:
            at_base, unjudged = Observation({}, True, False), unjudged or str(error)
        if not at_base.conclusive:
            unjudged = unjudged or (
                f"{file} does not load at the base: fix it on the default branch, or pass "
                "--base a commit where it loads"
            )
        new = [test for test in sorted(held) if test not in (at_base.outcomes or {})]
        if unjudged:
            return [(test, Verdict("not-judged", reason=unjudged)) for test in new]
        return [(test, self.judge(test, file)) for test in new]

    def held_tests(self, file: str) -> tuple[dict[str, str] | None, str]:
        """The tests the file holds at the newest record, and why they cannot be judged ("" when
        they can). When the newest run cannot say, the last run that did, if any."""
        last = len(self.history) - 1
        try:
            newest = self.observe(last, file)
        except NotJudged as error:
            return self.last_known(file, last), str(error)
        if newest.conclusive:
            return newest.outcomes or {}, ""
        reason = (
            f"{file} does not load at the newest record: make it load"
            if newest.outcomes is not None
            else f"the command wrote no JUnit for {file}: check `run` and the environment"
        )
        return self.last_known(file, last), reason

    def last_known(self, file: str, last: int) -> dict[str, str] | None:
        """The tests of the file's last conclusive run before `last` that reported any."""
        try:
            j = self.conclusive_before(last, file)
            known = self.observe(j, file).outcomes if j is not None else None
        except NotJudged:
            return None
        # An empty run from before the file was written says nothing about what it holds now.
        return known or None

    def judge(self, test: str, file: str) -> Verdict:
        """The test's verdict, or not-judged when a run it depends on could not be made."""
        try:
            return self.verdict(test, file)
        except NotJudged as error:
            return Verdict("not-judged", reason=str(error))

    def verdict(self, test: str, file: str) -> Verdict:
        """The test's verdict along the history (data-model.md, Verdict)."""
        birth = self.birth(test, file)
        if birth.at is None or birth.imported:
            return Verdict("unobserved")
        restored = self.restored(test, file, birth.at)
        if restored is not None:
            return restored
        life = self.follow(test, file, birth.at)
        if life.state != "first-pass":
            record = self.history[life.at].commit if life.at is not None else None
            return Verdict(life.state, record, life.reason)
        assert life.at is not None  # a first pass always has its record
        return self.judge_first_pass(test, file, life.at)

    def restored(self, test: str, file: str, b: int) -> Verdict | None:
        """The accepted verdict of an earlier stretch whose file the birth at b brought back
        unchanged (a stash and pop, an undone rename), or None (data-model.md, Restored).

        The code beside the restored test is not compared: deleting an accepted test with its
        code to write it back beside other code is forging, outside the threat model (R0).
        """
        touching = [i for i in range(1, b) if file in self.change(i)]
        here = self._blob(b, file)
        for n, t in enumerate(touching):
            if self._blob(t, file) != here:
                continue
            end = touching[n + 1] - 1 if n + 1 < len(touching) else b - 1
            earlier = self.until(end).verdict(test, file)
            if earlier.kind in ACCEPTED:
                return earlier._replace(reason="restored unchanged after it was judged")
        return None

    def _blob(self, i: int, file: str) -> str:
        return quiet_git(self.worktree, "rev-parse", f"{self.history[i].tree}:{file}")

    def judge_first_pass(self, test: str, file: str, r1: int) -> Verdict:
        """A test whose first run, at r1, passed (data-model.md, Judged at first run)."""
        record = self.history[r1].commit
        tree = self.history[r1].tree
        bare = without_sources(self.worktree, self.config, tree)
        if (self.observe_tree(bare, file).outcomes or {}).get(test) == "passed":
            return Verdict(
                "born-green",
                record,
                "it passes without any source file: the run command reaches code outside the "
                "scratch worktree (make `run` use it), or the test exercises code outside "
                "`sources` (add its paths to `sources`, committed on its own)",
            )
        on_base = compose(self.worktree, self.config, tests_from=tree, rest_from=self.base_tree())
        if (self.observe_tree(on_base, file).outcomes or {}).get(test) == "passed":
            return Verdict("predates", record)
        changed = self.change(r1)
        replaced = self.refactor_of(test, file, r1, changed)
        if replaced:
            return Verdict("refactored", record, replaced=replaced)
        if any(ledger.classify(self.config, path) == "source" for path in changed):
            if self._blob(r1 - 1, file) and not self.observe(r1 - 1, file).conclusive:
                return Verdict("born-with-code", record, NEVER_LOADED)
            return Verdict("born-with-code", record)
        return Verdict("born-green", record)

    def refactor_of(self, test: str, file: str, r1: int, changed: set[str]) -> tuple[str, ...]:
        """The accepted tests of the feature a refactor at r1 replaced, or () when it is not one.

        A call that changed the test side and anything else is never a refactor of tests. The
        tests whose first run passed at r1 may be at most as many as the accepted tests that
        disappeared there (research R13); passing that count means deleting an accepted test to
        add an untested one, which is forging, outside the threat model (research R0).
        """
        test_side = {path for path in changed if ledger.classify(self.config, path) == "test"}
        if test_side and test_side != changed:
            return ()
        files = sorted(test_side) if test_side else [file]
        gone: list[str] = []
        appeared: list[str] = []
        for f in files:
            before, after = self.observe(r1 - 1, f), self.observe(r1, f)
            if not (before.conclusive and after.conclusive):
                continue  # a file that did not load on either side says nothing
            was, now = before.outcomes or {}, after.outcomes or {}
            gone += [case for case in was if case not in now and self.accepted_before(case, f, r1)]
            appeared += [
                case for case, outcome in now.items() if outcome == "passed" and case not in was
            ]
        if gone and test in appeared and len(appeared) <= len(gone):
            return tuple(sorted(gone))
        return ()

    def accepted_before(self, case: str, file: str, r: int) -> bool:
        """Whether a test that disappeared at r was a test of the feature with an accepted
        verdict, judged along the history up to the record before r."""
        if case in (self.observe_tree(self.base_tree(), file).outcomes or {}):
            return False
        return self.until(r - 1).verdict(case, file).kind in ACCEPTED

    def until(self, newest: int) -> Auditor:
        """This auditor with its history ending at record `newest`."""
        earlier = copy.copy(self)
        earlier.history = self.history[: newest + 1]
        return earlier

    def base_tree(self) -> str:
        if self._base_tree is None:
            base = resolve_base(self.worktree, self.base_override)
            self._base_tree = ledger.git(self.worktree, "rev-parse", f"{base}^{{tree}}")
        return self._base_tree

    def follow(self, test: str, file: str, born: int) -> Lifecycle:
        """Forward from the birth: its first run, and when that failed, its green check."""
        red = False
        for k in range(born, len(self.history)):
            outcome = (self.observe(k, file).outcomes or {}).get(test)
            if outcome == "failed":
                red = True
            elif outcome == "passed":
                return self.green_check(test, file, k) if red else Lifecycle("first-pass", k)
        return Lifecycle("still-red" if red else "never-run", None)

    def green_check(self, test: str, file: str, g: int) -> Lifecycle:
        """Red only if the code at g satisfies the test side as it stood before g."""
        before = compose(
            self.worktree,
            self.config,
            tests_from=self.history[g - 1].tree,
            rest_from=self.history[g].tree,
        )
        seen = self.observe_tree(before, file)
        if not seen.conclusive:
            return Lifecycle(
                "not-judged",
                g,
                "the test side from before this call does not load against its code: change "
                "shared test support in a call of its own, before the code",
            )
        if (seen.outcomes or {}).get(test) == "passed":
            return Lifecycle("red", g)
        return Lifecycle("rewritten-to-green", g)

    def conclusive_before(self, t: int, file: str) -> int | None:
        """The nearest record before t whose run of the file is conclusive."""
        for j in range(t - 1, -1, -1):
            if self.observe(j, file).conclusive:
                return j
        return None

    def change(self, i: int) -> set[str]:
        """The paths record i changed against its previous in the effective history; the
        first asked computes every record's at once."""
        pair = (self.history[i - 1].tree, self.history[i].tree)
        if pair not in self._changes:
            trees = (record.tree for record in self.history)
            missing = list({p for p in itertools.pairwise(trees) if p not in self._changes})
            self._changes.update(
                zip(missing, changed_paths_of(self.worktree, missing), strict=True)
            )
        return self._changes[pair]

    def observe(self, i: int, file: str) -> Observation:
        return self.observe_tree(self.history[i].tree, file)

    def observe_tree(self, tree: str, file: str) -> Observation:
        """A run's observation; a run past its deadline makes the judgement impossible."""
        seen = self.replayer.observe(tree, file, self.deadline)
        if seen.timed_out:
            raise NotJudged(
                f"a replay of {file} exceeded its {self.deadline}-second deadline: "
                "run the audit with a longer --deadline"
            )
        return seen


def exit_status(verdicts: list[tuple[str, Verdict]]) -> int:
    """0 when every new test is accepted or never ran, 1 otherwise (FR-010)."""
    passing = ACCEPTED | {"never-run"}
    return 0 if all(verdict.kind in passing for _, verdict in verdicts) else 1


def seconds_from(least: int) -> Callable[[str], int]:
    """Whole seconds from `least` to run-bounded.sh's 999999999, or a usage error (exit 2): a
    deadline of 0 kills every run, while a budget of 0 judges from the runs already made."""

    def seconds(text: str) -> int:
        value = int(text)  # argparse turns its ValueError into the same usage error
        if not least <= value <= 999_999_999:
            raise argparse.ArgumentTypeError(f"{text!r}: seconds are {least} to 999999999")
        return value

    return seconds


def main(argv: list[str]) -> int:
    """The audit's command line (contracts/audit.md), and the Stop hook with `--stop`
    (contracts/ledger-hook.md)."""
    parser = argparse.ArgumentParser(prog="audit.py", description=__doc__)
    parser.add_argument("--base", help="the commit new tests are new against")
    parser.add_argument(
        "--deadline", type=seconds_from(1), help="seconds per replay (300; 60 with --stop)"
    )
    parser.add_argument("--stop", action="store_true", help="run as the Stop hook (JSON on stdin)")
    parser.add_argument(
        "--budget", type=seconds_from(0), default=120, help="with --stop: seconds in all"
    )
    args = parser.parse_args(argv)
    if args.stop:
        return _stop(args.budget, args.deadline or 60)
    try:
        worktree, config = _preconditions(Path.cwd(), args.base)
    except Refusal as refusal:
        print(f"test-first audit: {refusal}", file=sys.stderr)
        return 2
    try:
        verdicts, history = _audit(worktree, config, "audit", args.deadline or 300, args.base, None)
    except (subprocess.CalledProcessError, ledger.RecordError, OSError) as error:
        print(f"test-first audit: {_error_message(error)}", file=sys.stderr)
        return 2
    print(render(verdicts, history))
    return exit_status(verdicts)


def _error_message(error: Exception) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        return f"git failed: {(error.stderr or str(error)).strip()}"
    return str(error)


# What a Stop blocks on: failing verdicts that no later call can change (data-model, Verdict).
FINAL_FAILING = frozenset({"born-with-code", "born-green", "rewritten-to-green"})


def _stop(budget: int, deadline: int) -> int:
    """The Stop hook: block the turn once when a new test has a final failing verdict."""
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return 0  # one block per turn: this stop continues one a Stop hook already blocked
    try:
        worktree, config = _preconditions(Path(payload["cwd"]), None)
    except NothingToJudge:
        return 0
    except Refusal as refusal:
        print(f"test-first audit: {refusal}", file=sys.stderr)
        return 2
    try:
        verdicts, history = _audit(
            worktree, config, "Stop", deadline, None, budget, payload["session_id"]
        )
    except (subprocess.CalledProcessError, ledger.RecordError, OSError) as error:
        # An audit that cannot run -- git failing, no space for a replay or the memo -- blocks
        # with its error, so the turn never ends unjudged.
        print(f"test-first audit: {_error_message(error)}", file=sys.stderr)
        return 2
    if not any(verdict.kind in FINAL_FAILING for _, verdict in verdicts):
        return 0
    print(render(verdicts, history, listed=FINAL_FAILING), file=sys.stderr)
    return 2


def _audit(
    worktree: Path,
    config: ledger.Config,
    tool: str,
    deadline: int,
    base: str | None,
    budget: int | None,
    session: str | None = None,
) -> tuple[list[tuple[str, Verdict]], dict[str, Record]]:
    # Edits made between calls are judged too: the worktree as it is now is a record.
    call: ledger.Call = {"session": session or tool, "agent": None, "tool": tool, "call": None}
    ledger.record(worktree, call, config)
    with Replayer(worktree, config, budget) as replayer:
        auditor = Auditor(worktree, config, replayer, deadline, base)
        verdicts = auditor.report()
    return verdicts, {record.commit: record for record in auditor.history}


REDO = (
    "redo it: remove the test -- its file, when it is the file's only test -- revert the code "
    "it covers, write the test again in a call that changes nothing else, run it and see it "
    "fail, then restore the code"
)
# A test whose file did not load until its code existed (an import of a module not written yet)
# never ran before that code: the failure the agent saw was the import's, not the test's.
NEVER_LOADED = (
    "its file did not load before this call (it imports code that did not exist yet), so the "
    "test never ran before its code. Redo it with a stub: remove the test, revert the code, "
    "write a stub of the code in a call of its own, write the test in another call and see it "
    "fail, then write the code"
)
REMEDIES = {
    "born-with-code": REDO,
    "born-green": REDO,
    "rewritten-to-green": REDO,
    "still-red": "write the code that makes it pass, in a call that changes no test-side path",
    "unobserved": REDO + " (that gives it a birth in this ledger)",
}


def render(
    verdicts: list[tuple[str, Verdict]],
    records: dict[str, Record],
    listed: frozenset[str] | None = None,
) -> str:
    """The report: one line per new test, grouped by verdict, then a summary of every new test
    (contracts); with `listed`, only tests with those verdicts get their line (the Stop's)."""
    lines = []
    for kind in sorted({v.kind for _, v in verdicts if listed is None or v.kind in listed}):
        for test, verdict in verdicts:
            if verdict.kind != kind:
                continue
            record = records.get(verdict.record or "")
            where = f"{record.commit} {record.tool} {record.call or '-'}" if record else "- - -"
            lines.append(f"{kind} {test} {where}")
            lines.extend(f"  replaced {replaced}" for replaced in verdict.replaced)
            # A reason carries its own remedy (born-green without sources, not-judged).
            if verdict.reason:
                lines.append(f"  {verdict.reason}")
            elif kind in REMEDIES:
                lines.append(f"  {REMEDIES[kind]}")
    counts = Counter(verdict.kind for _, verdict in verdicts)
    tally = ", ".join(f"{kind} {count}" for kind, count in sorted(counts.items()))
    outcome = "pass" if exit_status(verdicts) == 0 else "FAIL"
    lines.append(f"audit: {len(verdicts)} new tests: {tally}; {outcome}")
    return "\n".join(lines)


class Refusal(Exception):
    """The audit cannot run here; the message says why (exit 2). A Stop hook blocks on it."""


class NothingToJudge(Refusal):
    """A refusal that only means there is nothing to judge here: a Stop hook lets the turn
    end (FR-024)."""


def _preconditions(cwd: Path, base: str | None) -> tuple[Path, ledger.Config]:
    root = quiet_git(cwd, "rev-parse", "--show-toplevel")
    if not root:
        raise NothingToJudge("not inside a git worktree")
    worktree = Path(root)
    try:
        config = ledger.load_config(worktree)
    except ledger.NotInstalled:
        raise NothingToJudge(f"not installed here: no {ledger.CONFIG}") from None
    except ledger.ConfigError as error:
        raise Refusal(str(error)) from None
    if not RUNNER.is_file():
        # Every replay runs under it (FR-011); without it each would read as "no JUnit".
        raise Refusal(f"{RUNNER} is missing: reinstall the test-first preset")
    if not quiet_git(worktree, "symbolic-ref", "--quiet", "HEAD"):
        raise NothingToJudge("HEAD is detached: check out the feature's branch")
    if not quiet_git(worktree, "rev-parse", "--verify", "--quiet", ledger.REF):
        message = f"no ledger in this worktree ({ledger.REF}): nothing was recorded"
        raise NothingToJudge(message)
    try:
        resolve_base(worktree, base)
    except BaseError as error:
        if error.on_default_branch:
            raise NothingToJudge(str(error)) from None
        raise Refusal(str(error)) from None
    return worktree, config
