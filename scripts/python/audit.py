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


class BaseError(Exception):
    """No base to judge new tests against."""


def resolve_base(worktree: Path, override: str | None = None) -> str:
    """The commit new tests are new against (data-model.md, Base)."""
    if override is not None:
        return _git(worktree, "rev-parse", "--verify", f"{override}^{{commit}}")
    if "origin" in _quiet_git(worktree, "remote").split():
        # Remote-tracking first: a local merge into the default branch cannot move these.
        named = _quiet_git(worktree, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
        candidates = [named.removeprefix("refs/remotes/"), "origin/main", "origin/master"]
    else:
        configured = _quiet_git(worktree, "config", "init.defaultBranch")
        candidates = [configured, "main", "master"]
    tried = [ref for ref in candidates if ref]
    default = next(
        (ref for ref in tried if _quiet_git(worktree, "rev-parse", "--verify", "--quiet", ref)),
        None,
    )
    if default is None:
        raise BaseError(f"no default branch to take the base from: tried {', '.join(tried)}")
    branch = _quiet_git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch == default.removeprefix("origin/"):
        raise BaseError(f"HEAD is on the default branch, {branch}: nothing is new against it")
    return _git(worktree, "merge-base", "HEAD", default)


def _quiet_git(worktree: Path, *args: str) -> str:
    """git's output, or "" when the command fails (an absent ref, for instance)."""
    result = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


class Record(NamedTuple):
    commit: str
    tree: str
    branch: str | None
    head: str


def effective_history(records: list[Record], branch: str) -> list[Record]:
    """The records of the branch's line of work, oldest first (data-model.md).

    Walking back from the branch's newest record with a current lineage: a record on the
    lineage is included; one off it is skipped when the lineage has an older record (a visit
    elsewhere and back), and otherwise included as the line the lineage came from.
    """
    lineage: str | None = branch
    line: list[Record] = []
    newest = max((i for i, record in enumerate(records) if record.branch == branch), default=-1)
    for i in range(newest, -1, -1):
        record = records[i]
        if record.branch != lineage:
            if any(older.branch == lineage for older in records[:i]):
                continue
            lineage = record.branch
        line.append(record)
    return line[::-1]


def load_records(worktree: Path) -> list[Record]:
    """The worktree's ledger, oldest record first; empty when there is none."""
    log = _quiet_git(worktree, "log", "--reverse", "-z", "--format=%H %T %B", ledger.REF, "--")
    records = []
    for entry in filter(None, log.split("\0")):
        commit, tree, message = entry.split(" ", 2)
        fields = json.loads(message)
        records.append(Record(commit, tree, fields["branch"], fields["head"]))
    return records


def changed_paths(worktree: Path, before: str, after: str) -> set[str]:
    """The paths whose presence or content differs between two trees (data-model.md, Change)."""
    listing = _git(worktree, "diff-tree", "-r", "-z", "--no-renames", "--name-only", before, after)
    return set(filter(None, listing.split("\0")))


class Birth(NamedTuple):
    at: int | None
    imported: bool = False
    restored_from: int | None = None


class NotJudged(Exception):
    """A run the judgement depends on could not be made; the reason says why."""


class Lifecycle(NamedTuple):
    """Where a test's life from its birth ended: its state, the record, and why."""

    state: str
    at: int | None
    reason: str = ""


class Verdict(NamedTuple):
    """An audit's judgement of one test: its name, the record it rests on, and why."""

    name: str
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
        branch = _git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
        self.history = effective_history(load_records(worktree), branch)

    def birth(self, test: str, file: str) -> Birth:
        """Where the test last appeared after being absent (data-model.md, Finding a birth).

        Walks back over the records that changed the test's file: one run there and one before
        decide most births. A test that appeared without its file changing (its file started to
        load, or its id comes from code or data) is found by a scan forward from where it was
        last seen absent.
        """
        touching = [i for i in range(1, len(self.history)) if file in self.change(i)]
        resume = len(self.history)
        for t in reversed(touching):
            if t >= resume:
                continue
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
            resume = j + 1
        origin = self.observe(0, file)
        if origin.conclusive and test not in (origin.outcomes or {}):
            return self.scan(test, file, 0)
        return Birth(None)

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
        if record.head != previous.head:
            committed = _git(self.worktree, "rev-parse", f"{record.head}^{{tree}}")
            seen = self.observe_tree(committed, file)
            if test in (seen.outcomes or {}):
                return Birth(b, imported=True)
        return Birth(b)

    def verdict(self, test: str, file: str) -> Verdict:
        """The test's verdict along the history (data-model.md, Verdict)."""
        birth = self.birth(test, file)
        if birth.at is None or birth.imported:
            return Verdict("unobserved")
        life = self.follow(test, file, birth.at)
        if life.state != "first-pass" or life.at is None:
            record = self.history[life.at].commit if life.at is not None else None
            return Verdict(life.state, record, life.reason)
        return self.judge_first_pass(test, file, life.at)

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
        if any(ledger.classify(self.config, path) == "source" for path in changed):
            return Verdict("born-with-code", record)
        return Verdict("born-green", record)

    def base_tree(self) -> str:
        if self._base_tree is None:
            base = resolve_base(self.worktree, self.base_override)
            self._base_tree = _git(self.worktree, "rev-parse", f"{base}^{{tree}}")
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
        """The paths record i changed against its previous in the effective history."""
        return changed_paths(self.worktree, self.history[i - 1].tree, self.history[i].tree)

    def observe(self, i: int, file: str) -> Observation:
        return self.observe_tree(self.history[i].tree, file)

    def observe_tree(self, tree: str, file: str) -> Observation:
        """A run's observation; a run past its deadline makes the judgement impossible."""
        seen = self.replayer.observe(tree, file, self.deadline)
        if seen.timed_out:
            raise NotJudged(f"a replay of {file} exceeded its {self.deadline}-second deadline")
        return seen
