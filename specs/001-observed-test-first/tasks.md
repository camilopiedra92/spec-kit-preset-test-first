---

description: "Task list for feature 001-observed-test-first"
---

# Tasks: Observed test-first

**Input**: Design documents from `/specs/001-observed-test-first/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: required (this preset's test-first rules). Each behaviour task carries its test list as
plain bullets under it: one case per line, simplest first. Implementation turns them into tests
one at a time and adds the cases it finds.

**Organization**: by user story, in the spec's priority order. A story's tasks are sequential.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: the user story (US1–US5)

Paths: `scripts/python/` (the hook and the audit, standard library only, run as `python3 <path>`),
`scripts/bash/` (the 1.x gate's installer, the deadline runner; the ledger's installer is in
`scripts/python/`, research R16), `tests/python/` (pytest units), `tests/*.sh` (end-to-end
suites in scratch repositories), `commands/` (fragments).

---

## Phase 1: Setup

- [X] T001 Add the Python toolchain as its own change: `pyproject.toml` with a uv dev group
  (ruff, mypy, pytest, pytest-timeout), `[tool.uv] package = false`, `requires-python = ">=3.11"`,
  mypy strict with `python_version = "3.11"` over `scripts/python` and `tests/python`, ruff
  `target-version = "py311"`, pytest `timeout` set and `testpaths = ["tests/python"]`; `uv.lock`
  committed. The 3.11 floor (3.10 reached its end of life on 2026-10-01; Spec Kit's own) because the scripts run on other projects' `python3` (plan, Technical
  Context; research R11; approved defaults in the global rules)
- [X] T002 Export-ignore `pyproject.toml`, `uv.lock` and `docs/` in `.gitattributes`, and make
  `tests/compose.sh` fail when the installed preset carries any of them (constitution V, 1.1.0)
  - an archive built from a commit that drops one of the three `.gitattributes` lines → compose.sh
    names that path and exits non-zero (break it on purpose, then restore)
    - red: `tests/compose.sh` on a commit without the lines → `FAIL: the installed preset carries
      this repository's pyproject.toml` and `… uv.lock`; on a probe commit adding `docs/probe.md`
      without its line → `FAIL: … carries this repository's docs`
  - the archive of HEAD with all three lines → no complaint about them
    - green: `ok: composes on specify 1.1.0` at cc4dc2b
- [X] T003 Run the Python checks and the new suites in CI as steps of the existing `compose` job in
  `.github/workflows/ci.yml` — `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`,
  `uv run pytest` (also under Python 3.11, `uv run --isolated --python 3.11 pytest`), `tests/ledger.sh`,
  `tests/install-ledger.sh`, `tests/audit.sh` — so the required `compose (pinned)` check covers
  them (plan, "CI"; FR-023; constitution IV). Each suite step is added by the task that creates the
  suite; this task adds the Python steps and the order

---

## Phase 2: Foundational (the ledger records; blocks US1 and US2)

- [X] T004 Read and validate `.specify/test-first.json` in `scripts/python/ledger.py`
  (data-model "Configuration"; contracts/configuration.md; FR-013)
  - a valid file with `tests`, `sources` and `run` → a configuration object
    - red: `uv run pytest` → `NotImplementedError` from the stub `load_config`
  - `tests` empty, or not a list of strings → error naming the field
    - red: `DID NOT RAISE ConfigError` (empty; `"tests/**"`, `[1]`, `[""]`)
  - `sources` empty → error naming the field
    - red: `DID NOT RAISE ConfigError` (`[]`, `"src/**"`, `[3]`)
  - `run` without `{file}` → error; without `{junit}` → error; with `{root}` → accepted
    - red: `DID NOT RAISE ConfigError` for the three; `{root}` passed on its first run (nothing
      rejected it yet): rejecting `{root}` on purpose failed it, restored
  - the file missing → "not installed" (distinct from malformed)
    - red: `FileNotFoundError` once `NotInstalled` was stubbed
  - invalid JSON → error with the parser's message
    - red: `json.decoder.JSONDecodeError` escaped instead of `ConfigError`
  - a JSON value that is not an object → error (found during implementation)
    - passed on its first run (the check was written ahead of its test); disabling the check on
      purpose failed it with `AttributeError: 'list' object has no attribute 'get'`, restored
- [X] T005 Classify paths in `scripts/python/ledger.py`: test / source / other, and mixed changes
  (data-model "Configuration", "Change"; FR-005)
  - `tests/a.py` with `tests = ["tests/**"]` → test
    - red: `AttributeError: … no attribute 'classify'`, then `assert '' == 'test'` from the stub
  - `tests/a/b/c.py` → test (`**` crosses directories)
    - passed on its first run (`fnmatch`'s `*` crosses `/`); requiring equal slash counts on purpose
      failed it (`assert 'other' == 'test'`), restored
  - `src/x.py` with `sources = ["src/**"]` → source
    - red: `assert 'other' == 'source'`
  - a path matching both lists → test
    - passed on its first run (tests were checked first); checking sources first on purpose failed
      it (`assert 'source' == 'test'`), restored (a stale `.pyc` first served the broken version:
      runs since use `PYTHONDONTWRITEBYTECODE=1`)
  - `README.md`, `specs/001/tasks.md` → other
    - passed on its first run; returning `source` for unmatched paths on purpose failed it, restored
  - a change of one test and one source path → mixed; tests and other only → not mixed
    - red: `AttributeError: … no attribute 'is_mixed'`, then `assert False` from the stub
  - whether `**/test_*.py` matches a root-level `test_x.py` (found during implementation; was
    `stopped: possible spec gap`, decided by the owner on 2026-10-07: git's semantics, research
    R15 and data-model "Configuration")
    - red: `assert 'other' == 'test'` under `fnmatch`; a wildmatch translation fixed it. Written
      whole in that step, so the next cases passed on their first run: `*` within a segment, and
      every glob of a table matching exactly what `git ls-files ':(glob)…'` matches. Going back to
      `fnmatch` on purpose failed all three; `**/` requiring a directory failed two; restored
- [X] T006 Snapshot the worktree as a tree in `scripts/python/ledger.py`: temporary index seeded
  from the worktree's own, `git add -A`, `git write-tree`; tracked and untracked-but-not-ignored
  files; the real index and the worktree never modified (research R2; FR-001; constitution IV)
  - a clean repository → the HEAD commit's tree
    - red: `AttributeError: … no attribute 'snapshot'`, then `assert '' == 'dc7a7dd…'` from the stub
  - an untracked file → in the tree; an ignored one → not
    - passed on its first run; `git add -u` on purpose failed it (`'src/new.py' in {…}`), and
      `git add -A -f` on purpose (`'debug.log' not in {…}`), restored
  - a deleted tracked file → absent from the tree
    - passed on its first run; `git add --ignore-removal .` on purpose failed it, restored
  - staged and unstaged edits of one file → the worktree's content
    - passed on its first run; writing the tree from the real index on purpose failed it
      (`'A = 2' == 'A = 3'`), restored
  - after the snapshot, `git status --porcelain` and `.git/index` byte-identical to before
    - its first run failed against correct code: the test read the index before `git status`,
      which refreshes it; reordered (expectation unchanged); `git add -A` on the real index on
      purpose then failed it, restored
  - a same-size edit made in the second the index was written is seen (found during T020: the
    intermittent failure first noticed in T012)
    - root cause: copying the index with `shutil.copyfile` gave the copy a fresh mtime, which
      disables git's racy-entry recheck; measured 10 of 10 edits missed with the snapshot started
      in the next second, 0 of 10 with `shutil.copy2`; at random timing 1 of 300 against 0 of 300
    - red: `assert 'A = 1' == 'A = 2'` three runs out of three; `copy2` fixed it
  - an older `python3` gets a message, not a traceback (found during implementation, 2026-10-07:
    the macOS `python3` is 3.9.6, below any floor; the floor raised from 3.10, past its end of
    life on 2026-10-01, to 3.11, Spec Kit's own)
    - red: `KeyError: 'cwd'` traceback under a patched 3.9 version; a guard at the top of each
      script, then one entry point `cli.py` (the guard before any import: no lint exception);
      under a real Python 3.9 (`tests/ledger.sh`), exit 2 with `needs python3 >= 3.11, found
      3.9`; an `except*` added on purpose made 3.9 fail to parse it, restored
- [X] T007 Append a record in `scripts/python/ledger.py`: `git commit-tree <tree> -p <previous>`
  with the message JSON `time`, `session`, `agent`, `tool`, `call`, `branch`, `head`; move
  `refs/worktree/test-first/ledger` with `git update-ref <ref> <new> <old>`, retried on a race;
  no record when the tree equals the newest record's (data-model "Record"; FR-002; FR-003)
  - first snapshot of a worktree → one record, no parent
    - red: `AttributeError: … no attribute 'record'`, then `rev-list refs/worktree/test-first/ledger`
      failed (exit 128) under the stub
  - same tree again → no new record
    - red: `assert 'b7bb0a7…' is None`
  - a changed tree → a record whose parent is the previous newest
    - passed on its first run; dropping the parent on purpose failed it, restored
  - message JSON carries all seven fields; `agent` null without `agent_id`; `branch` null when
    detached
    - red: `assert {'agent', 'call', 'session', 'tool'} == {… 'time', …}` (no time, branch, head)
  - a concurrent update between read and write → retried, both records in the chain
    - red: the racing record was overwritten (`At index 1 diff: '4647c50…' != 'a154539…'`)
  - losing every race → an error, never a silently dropped record (found during implementation)
    - passed on its first run (the error path was written with the retry); returning `None` on
      purpose failed it (`DID NOT RAISE RecordError`), restored
  - a linked worktree → its own ref, the main worktree's chain untouched
    - passed on its first run (a git property of `refs/worktree/`); a shared
      `refs/test-first/ledger` on purpose failed it, restored
  - `git gc --prune=now` → every record still reachable
    - passed on its first run (reachable from the ref); in a scratch repository, deleting the ref
      before `gc --prune=now` made the record's object unreadable (`cat-file: could not get object
      info`), which is what the test detects
- [X] T008 The `PostToolUse` entry point of `scripts/python/ledger.py`: read the hook JSON from
  stdin (`cwd`, `session_id`, `agent_id`, `tool_name`, `tool_use_id`), resolve the worktree of
  `cwd`, snapshot and append; exit 0 silently when not in a git worktree or not installed; exit 2
  with the error on stderr when recording fails (contracts/ledger-hook.md steps 1–3 and failures;
  FR-001; FR-004)
  - `cwd` outside any git repository → exit 0, no output
    - red: `AttributeError: … no attribute 'post_tool_use'`, then `NotImplementedError` from the stub
  - a repository without `.specify/test-first.json` → exit 0, no output
    - red: a record was made (`assert 'befc36d… refs/worktree/test-first/ledger' == ''`)
  - installed, a changed file → exit 0, one record with the input's session, tool and call
    - red: `git log … refs/worktree/test-first/ledger` exit 128: nothing recorded
  - a subagent's input with `agent_id` → the record carries it
    - passed on its first run; dropping `agent_id` on purpose failed it (`None == 'agent-7'`), restored
  - `cwd` in a subdirectory or a linked worktree → that worktree's ledger
    - passed on its first run; resolving the main worktree on purpose failed it, restored
  - a malformed configuration → exit 2, stderr names it, no record
    - red: `ConfigError` escaped the hook
  - git unable to write (objects directory read-only) → exit 2, stderr has git's error, worktree
    and real index unchanged
    - red: `CalledProcessError` from `git add -A` escaped the hook
  - a source and a test written by one Bash heredoc → one record holding both
    - red: `tests/ledger.sh` → `FAIL: the record lacks tests/test_b.py` (no script entry point yet)
  - one snapshot of a ~1,000-file scratch repository → under 100 ms, median of five (SC-003)
    - red: `FAIL: a record took 149 ms` (the instrument counted a timer's own start-up; timed from
      one process instead: 99 ms of five, too close); cutting git processes and the dataclass
      import brought medians to 80–83 ms of eleven; a 50 ms pause on purpose failed it (145 ms),
      restored. Enforced off CI, reported on CI: SC-003 is defined on the development machine
  - these cases end to end, with recorded hook inputs in scratch repositories, in `tests/ledger.sh`
    (quickstart step 2), added as a step of the CI `compose` job (T003)

---

## Phase 3: User Story 1 — A test written together with its code is caught (P1) 🎯 MVP

**Goal**: the audit judges every new test from the ledger and replays, and fails on code-first.

**Independent test**: in a scratch pytest repository with the ledger recording, replay "test then
code" and "test and code in one shell call"; the audit reports `red` and exits 0 for the first,
`born-with-code` and exits 1 for the second.

- [X] T009 [US1] Parse one JUnit XML file into test outcomes in `scripts/python/audit.py`
  (data-model "Run"; research R6; FR-008)
  - no file written → "no JUnit"
    - red: `ModuleNotFoundError: No module named 'audit'`, then `assert {} is None` from the stub
  - `tests="0"` and no `testcase` → conclusive, no tests
    - passed on its first run (the stub returned `{}`); returning `None` on purpose failed it, restored
  - one `testcase` without children → passed, id `classname::name`
    - red: `assert {} == {'tests.test_…ne': 'passed'}`
  - a `failure` child → failed; an `error` child → failed; a `skipped` child → skipped
  - pytest's `<skipped type="pytest.xfail">` → skipped
    - red (both, one test): every case read as `passed`
  - nested `testsuite` elements (Vitest, Jest) → every `testcase` found
    - passed on its first run (`iter` walks every level); one level only on purpose failed it, restored
  - malformed XML → "no JUnit" (treated as a run that wrote none)
    - red: `xml.etree.ElementTree.ParseError: unclosed token` escaped
- [X] T010 [US1] Run one test file in a scratch worktree in `scripts/python/audit.py`: one
  detached scratch worktree in a temporary directory, `git read-tree -u --reset <tree>`,
  `git clean -fdx`, the configured command through `sh -c` and
  `scripts/bash/run-bounded.sh <deadline>`, `{file}`, `{junit}` and `{root}` substituted and
  shell-quoted; stale scratch worktrees of an earlier killed audit pruned at start; removed on exit
  (research R7; FR-011; constitution IV)
  - a passing test file → its outcomes; the command ran with the scratch worktree as cwd
    - red: `AttributeError: … no attribute 'Replayer'`, then `assert None == {…}` from the stub
  - a file name with a space and a quote → substituted safely
    - passed on its first run; substituting without `shlex.quote` on purpose failed it, restored
  - a command that hangs → stopped at the deadline with its process group; "timed out"
    - passed on its first run (run-bounded.sh); a single-process `subprocess.run(timeout=…)` on
      purpose failed it (`a child of the command outlived the deadline`), restored
  - an untracked cache from a previous run (`__pycache__`) → gone before the next run
    - passed on its first run; dropping `git clean -fdx` on purpose failed it (`c::stale`), restored
  - `{root}` → the real worktree's absolute path
    - passed on its first run; substituting the scratch path on purpose failed it, restored
  - after the audit, `git worktree list` shows only the real worktrees; after a killed audit and a
    rerun, the same
    - red (killed): the dead audit's scratch worktree stayed registered
  - a running audit's scratch worktree is left alone (found during implementation: a Stop audit
    beside a story-close audit)
    - passed on its first run; pruning regardless of the owner on purpose failed it, restored
- [X] T011 [US1] Memoize runs in `scripts/python/audit.py` under
  `git rev-parse --git-path test-first/runs`, keyed by (tree id, file, hash of `run`) (data-model
  "Run", Memo; FR-026)
  - the same key twice → the command runs once
    - red: `assert 2 == 1` (no memo)
  - a different `run` string → runs again
    - passed on its first run; a key without the command on purpose failed it (`1 == 2`), restored
  - a run that wrote no JUnit → not stored; runs again next time
    - passed on its first run; storing every run on purpose failed it (`1 == 2`), restored
  - a timed-out run stored with its deadline → not retried under the same or a shorter deadline;
    retried under a longer one
    - passed on its first run; never retrying on purpose failed it (`assert not True`), restored
  - the memo directory deleted → the next audit gives the same verdicts
    - passed on its first run, and nothing short of a nondeterministic run could break it: it
      pins that the memo is only a cache (the run count shows the second audit really ran)
- [X] T012 [US1] Build the replay trees in `scripts/python/audit.py` with git plumbing, without
  touching the real index: before-version of *g*, base overlay of *r*, no-sources of *r*, and the
  load probe's tree (data-model "Run", variants; research R5; FR-028)
  - before-version → every test-side path from *g*'s previous, every other path from *g*
    - red: `AttributeError: … no attribute 'compose'`, then the stub returned the whole previous tree
  - base overlay → every test-side path from *r*, every other path from the base, a path the base
    lacks removed
    - passed on its first run (same `compose`); swapping only source paths on purpose failed it, restored
  - a template outside `sources` changed at *r* → the base overlay has the base's template
    - same test as the overlay (`templates/x.html` is the base's); the break above failed it
  - no-sources → every `sources` path removed, configuration files kept
    - red: the stub returned the tree unchanged
  - load probe → the file's content replaced by bytes no language parses, nothing else changed
    - red: the stub returned the tree unchanged
  - paths with unusual characters (`año test.py`) are classified by their real name (found during
    implementation: `ls-tree` quotes them without `-z`)
    - red: the test path was taken from the rest side; NUL-separated, unquoted listing fixed it
- [X] T013 [US1] Decide whether a run is inconclusive in `scripts/python/audit.py`: no JUnit, or
  every case failed and the load probe on the same tree and file reports exactly the same ids; the
  probe runs only when every case failed (data-model "Run"; research R6; FR-007)
  - a run with one passing case → conclusive, no probe
    - red: `AttributeError: 'Replayer' object has no attribute 'observe'`, then `NotImplementedError`
  - zero cases → conclusive
    - passed on its first run; probing an empty run on purpose (treating it as all-failed) failed
      it, restored
  - pytest collection failure (`classname=""`, `name=<module>`, error) and a probe with the same
    case → inconclusive
    - red: `assert not True` (every run was conclusive)
  - Vitest's file-named failure and a probe with the same case → inconclusive (skip when node is
    unavailable, and say so)
    - unit with Vitest's measured shape: passed on its first run; recognising only pytest's shape
      (empty classname) on purpose failed it, restored. The real Vitest run is in tests/audit.sh
  - every test genuinely failing by assertion → the probe reports a different id set → conclusive
    - passed on its first run; ignoring the probe's ids on purpose failed it, restored
- [X] T014 [US1] Resolve the base in `scripts/python/audit.py`: merge base with the
  remote-tracking default (`origin/HEAD`, else `origin/main`, else `origin/master`); without an
  `origin` remote, the local `init.defaultBranch`, `main`, `master`; refuse when none resolves or
  HEAD is on the default branch; no network (data-model "Base"; research R14; FR-027)
  - `origin/HEAD` → `origin/main` → its merge base with HEAD
    - red: `AttributeError: … no attribute 'resolve_base'`, then `assert '' == '8399dd6…'`
  - `origin` without `origin/HEAD` but with `origin/main` → that
    - first passed for the wrong reason: git 2.55 creates `origin/HEAD` on fetch
      (`followRemoteHEAD`); with it deleted, red: `merge-base HEAD ''` exit 128
  - no remote, local `main` → its merge base
    - red: `StopIteration` (only remote-tracking candidates)
  - a local merge into `main` after the branch's commits → base unchanged when `origin/main` exists
    - passed on its first run; preferring local `main` on purpose failed it, restored
  - HEAD on `main` → refusal naming it
    - red: `AttributeError: … 'BaseError'`, then `DID NOT RAISE BaseError`
  - nothing resolves → refusal naming what was tried
    - red: `AttributeError: … 'BaseError'`, then `StopIteration`
  - `--base <rev>` → that commit
    - first passed by coincidence (`HEAD~1` was the merge base); made distinguishable, red:
      `assert '7c2c5c4…' == '8df27c4…'`
  - an `origin` whose URL is unreachable → the base resolves from local refs; no fetch is made
  - without a remote, `init.defaultBranch` comes before `main` (added after the story 1 review:
    no case pinned it) — dropping it on purpose failed the case
  - `--base` on the default branch is honoured (decided after the review, FR-027) — refusing it
    on purpose failed the case
    - rewritten to detect a fetch (a remote whose main moved on, and `origin/main` checked);
      passed on its first run; a `git fetch` on purpose failed it (`the audit fetched`), restored
- [X] T015 [US1] Compute the effective history of the current branch from the ledger in
  `scripts/python/audit.py`, and each record's previous and change (data-model "Effective
  history")
  - one branch, five records → all five, each previous the one before
    - red: `AttributeError: … 'Record'`, then `assert [] == ['c0', …, 'c4']` from the stub
  - a visit to another branch and back → the visit's records skipped; the return compared with
    the branch's last record
    - passed on its first run (the lineage walk came with the next case); dropping the visit rule
      on purpose failed it, restored
  - `git checkout -b feat` with uncommitted work → the records before it, on the original branch,
    included; the new branch's first change compared with them
    - red: `assert ['c2', 'c3'] == ['c0', 'c1', 'c2', 'c3']`
  - a branch renamed mid-line → one continuous line
    - passed on its first run; not following the lineage on purpose failed it, restored
  - a rebase (detached records in between) → detached records skipped
    - passed on its first run; dropping the visit rule on purpose failed it, restored
  - the origin → no previous
    - a branch with no record has no history: passed on its first run; starting from the newest
      record of any branch on purpose failed it, restored
  - the ledger read back from git oldest first with branch and head; no ledger reads as none; a
    change is the set of paths that differ (`año.py` included)
    - red: `AttributeError: … 'load_records'` / `'changed_paths'`, then wrong values from the stubs
- [X] T016 [US1] Find a test's birth in `scripts/python/audit.py`: walk back over the records
  that touched its file, running the record before each; skip touching records whose run is
  inconclusive; scan forward when it appeared without its file changing; no birth back to the
  origin; imported when its birth record's HEAD moved to a commit already holding it; restored
  when its file is identical to an earlier accepted state (data-model "Finding a test's birth",
  "Restored", "Imported"; FR-007)
  - a test in a new file → born at the call that created the file
    - red: `AttributeError: … 'Auditor'`, then `assert None == 1` from the stub
  - a test added to a file written 300 records earlier → born at the adding call, with one extra
    run
    - with 8 records between: passed on its first run (2 runs); walking forward on purpose
      failed it (`assert 3 == 2`), restored
  - a file broken by a typo for one call, then fixed → born where first written, not at the fix
    - passed on its first run; the next case, a file that first loads at its fix, was red
      (`None`): the walk back through inconclusive records came from it
  - a file that cannot load until a stub is written by a source-only call → born at the stub's
    record
    - red: `assert None == 2` (no scan forward); the fake runner gained `# needs <path>`
  - present back to the origin → no birth
    - passed on its first run; scanning from the origin regardless on purpose failed it, restored
  - a file that never loaded back to the origin → no birth, fail closed (found during
    implementation: the test may predate the ledger)
    - red: `assert 1 is None`
  - removed and written again (the redo sequence) → born at the rewrite
    - passed on its first run; taking the oldest touching record on purpose failed it, restored
  - `git stash` then `git stash pop` in another call → restored with its earlier verdict
    - moved to T020: a restored birth keeps an earlier *accepted verdict*, which needs T018/T019
  - a test written and committed in one call → imported
    - red: `Birth(index=1) == Birth(index=1, imported=True)` failed; written then committed in its
      own call stays not imported
  - a test brought by `git merge` or `git pull` → imported
    - passed on its first run (the imported rule); dropping the rule on purpose failed it, restored
- [X] T017 [US1] Follow a test from its birth in `scripts/python/audit.py`: run its file at every
  record of the effective history until its first run that is not skipped, and, when that failed,
  until it passes; then the green check on the before-version (data-model "Test lifecycle"; FR-009)
  - test, red, then a source-only call → `red`
    - red: `AttributeError: … 'Lifecycle'`, then the stub's empty lifecycle
  - a red test whose expected value is changed in the same call as the code → `rewritten-to-green`
    - red: `red` returned (no green check yet)
  - a red test made to pass by changing only a test helper → `rewritten-to-green`
    - first run failed on bad test data (`EXPECTED` contains `X`; the test passed at birth);
      fixed the data; it then passed; running the green record's own tree on purpose failed it
  - a red test with a missing method that a later source call adds → `red` (scenario 6)
    - covered by the first case with the stand-in runner; with real pytest in tests/audit.sh
      (a missing method raising `AttributeError`) since the story 1 review
  - a red test edited until it passes in a test-only call → `rewritten-to-green` (scenario 9;
    no test had it until the story 1 review)
    - passed on its first run; a green check that always says red failed it on purpose
  - the crash the test reproduces, then the fix → `red`
    - covered by the first case for the same reason
  - one call changing an API and a shared fixture, so the before-version does not load →
    `not-judged`, reason and remedy named
    - red: `('rewritten-to-green', 2) == ('not-judged', 2)`; the stand-in gained `# uses <path>`
  - skipped at birth, unskipped and red later, then code → `red`
    - passed on its first run; counting a skip as a pass on purpose failed it, restored
  - still failing at the newest record → `still-red`; only skipped → `never-run`
    - red (never-run): `still-red` returned for a test that never ran
  - a replay past its deadline anywhere in the judgement → `not-judged` (found during
    implementation: a timed-out run read as "nothing seen")
    - red: `AttributeError: … 'NotJudged'`, then `DID NOT RAISE NotJudged`
- [X] T018 [US1] Judge a test whose first run passed in `scripts/python/audit.py`: steps 1–4 in
  order — no-sources pass, base-overlay pass, the refactor count in a call that is not two-sided,
  then by source in the change (data-model "Judged at first run"; research R7, R13; FR-009;
  FR-025)
  - test and code in one shell call → `born-with-code`, call named
    - red: `AttributeError: … 'Verdict'`, then `('', None)` from the stub
  - code first, then the test alone → `born-green`
    - passed on its first run; naming every first pass born-with-code on purpose failed it
  - a test moved from a file at the base, passing against the base → `predates`
    - red: `'born-green' == 'predates'`; the two earlier cases moved to a feature branch (on
      `main` the base refuses), expectations unchanged
  - a test that imports nothing from `sources` → `born-green`, reason "passes without sources"
    - red: `'predates' == 'born-green'` (no no-sources step)
  - an environment that imports the real worktree's code → a would-be `predates` is `born-green`
    with that reason
    - passed on its first run (the no-sources step); disabling the step on purpose failed it;
      the stand-in gained `--root` (paths from the real worktree)
  - a test-only call renaming one accepted test → `refactored`, listing it
    - red: `('born-green', …, ()) == ('refactored', …, ('tests.test_b::test_old',))`
  - three accepted tests merged into one parametrized test with three ids → `refactored`
    - passed on its first run; requiring exactly one replaced test on purpose failed it
  - a rename plus one more passing test in the same call → none refactored
    - passed on its first run; dropping the count on purpose failed it
  - a rename, a new case and its code in one mixed call → `born-with-code`
    - passed on its first run; dropping the two-sided rule on purpose failed it
  - an enum member renamed in code, renaming one parametrized id → `refactored`
    - passed on its first run; ignoring a code-only change's own file on purpose failed it; the
      stand-in gained `# params <list> <check>`
  - behaviour first written in a template outside `sources`, tested later → `born-green`
    - passed on its first run; with the no-sources step off and only source globs from the base,
      on purpose, it read `predates`, restored
- [X] T019 [US1] Determine the new tests and assemble the verdicts in `scripts/python/audit.py`:
  tests reported at the newest record by test files that differ from the base and absent from the
  base's runs; a file inconclusive at the newest record → its last conclusive tests `not-judged`;
  a dependent run past its deadline → `not-judged`; a test deleted before the end → not judged
  (data-model "Verdict"; FR-006; FR-010)
  - a new test in a changed file → judged; an existing test changed in the feature → not new
    - red: `AttributeError: 'Auditor' object has no attribute 'report'`, then `{}` from the stub
  - a test deleted before the end → absent from the report
    - passed on its first run (only the newest record's tests are candidates); taking candidates
      from every record would be the break, and is what the next case's red showed for a file
      that does not load
  - a test file broken at the newest record → its tests `not-judged`, exit 1
    - red: `['::tests.test_b'] == ['tests.test_b::test_b']` (the load-failure case reported as a
      test)
  - a command writing no JUnit at the newest record, and a file that does not load at the base →
    `not-judged` with their own reasons (found during implementation: the data model's reasons)
    - passed on their first run; both branches disabled on purpose failed them, restored; the
      stand-in gained `# nojunit`
  - a hanging replay → `not-judged`, exit 1, nothing left running
    - red: `audit.NotJudged: … exceeded its 1-second deadline` escaped the report
  - every test `red`, `predates`, `refactored` or `never-run` → exit 0, never-run listed
  - any other verdict → exit 1
    - red: `AttributeError: … 'exit_status'`
- [X] T020 [US1] The audit's command line in `scripts/python/audit.py`: `--base`, `--deadline`;
  snapshot first when the worktree differs from the newest record (`tool` = `audit`); refuse with
  exit 2 on a detached HEAD, HEAD on the default branch, no ledger, no configuration or no base;
  stdout lines `<verdict> <test id> <record> <tool> <call>` (`-` for `unobserved`), reasons and
  replaced tests, each failing verdict's remedy, and the summary line (contracts/audit.md; FR-012;
  FR-026)
  - a worktree edited after the last call → a record with `tool` = `audit` before judging
    - red: `AttributeError: … 'main'`, then `assert 'Bash' == 'audit'` from the stub
  - no ledger → exit 2, message; detached HEAD → exit 2
    - red: `ledger.NotInstalled` escaped; then the test's own last step was wrong (`main` had no
      configuration), fixed by moving `main` to the feature, expectation unchanged
  - a report → grouped by verdict, summary `audit: <n> new tests: …; pass|FAIL`
    - red: no output; then two wrong expectations of mine (call numbering starts at the origin's
      `c1`; `Record` gained `tool` and `call`), corrected
  - `born-with-code` → its line ends with the redo sequence
    - red: no output
  - the audit reads no `tasks.md`: a `tasks.md` claiming red runs changes nothing
    - passed on its first run (nothing reads it); trusting a `red:` line on purpose failed it
  - end to end in `tests/audit.sh`: ledgers built in a scratch pytest project by replaying recorded
    tool-call sequences through `cli.py ledger`, every case of quickstart step 4 and spec Story 1
    scenarios 1–12, verdicts and exit codes asserted (SC-001, SC-002), added as a step of the CI
    `compose` job (T003)
    - the story 1 review found this claimed more than it ran (scenarios 5b, 6, 9, 10, 11, 12 and
      15 quickstart items had units only); all now run with real pytest — 30 scenarios. Two of
      the new ones first failed on my data (scenario 11's expected verdict; macOS `wc -l`
      padding), corrected; pruning disabled on purpose failed the killed-audit scenario
    - red: every scenario failed with no output (no script entry point); then the moved-test
      scenario's data was wrong (its test exercised no source, rightly born green), fixed
    - the hang scenario found a fail-open: a file whose newest run timed out and whose tests no
      run had reported contributed no test, and the audit passed; now the file itself is
      `not-judged` (unit case added, red `[] == ['tests/test_b.py']`)
    - Vitest 5 scenario (a typo for one call): passed where node and pnpm are present
  - a second audit → reruns nothing (memo)
    - passed on its first run (the memo of T011)
  - a 60-test, 20-file feature → warm under 2 minutes, cold time reported (SC-004)
    - first measured cold 92 s, warm 71 s; caching each record's change: cold 27–29 s, warm 8–9 s
  - `git stash` then `git stash pop` in another call → restored with its earlier verdict (moved
    from T016: needs the verdicts of T018/T019)
    - red: `'born-with-code' == 'red'`; done with T019, where the verdicts are assembled

**Checkpoint**: US1 delivers the guarantee; the audit can be run by hand.

---

## Phase 4: User Story 2 — The agent hears it at once (P2)

**Goal**: a mixed call is reported after the call; a final failing verdict blocks the turn once.

**Independent test**: with the ledger recording in a scratch repository, a call changing a test
and a source file returns the message; a test-only call returns none; ending the turn after a
born-with-code test is blocked once, and the next stop passes.

- [X] T021 [US2] Report a mixed call in `scripts/python/ledger.py`: exit 2 with stderr naming the
  test paths and the source paths, saying that a test added or changed with the code that
  satisfies it will fail the audit, and the redo sequence (research R4; contracts/ledger-hook.md
  step 4; FR-005)
  - a call changing `tests/t.py` and `src/x.py` → exit 2, both named
    - red: `assert 0 == 2`
  - only tests, only sources, or neither → exit 0, no output
    - passed on their first run; telling every changed call on purpose failed them, restored
  - tests and `README.md` → exit 0 (documentation is neither)
    - same test as above (third parameter)
  - a symbol renamed across code and tests → exit 2, the message worded as conditional
    - red: the first message had no condition; then the test compared exact line breaks,
      normalised (content unchanged)
    - cost: the first version took the hook to 97–104 ms (over SC-003); a diff-index from the
      snapshot's own index, limited by `:(glob)` pathspecs, brought it to 84–87 ms (research L7)
  - found by the story 2 review: a reftable repository → the branch named, not `.invalid`
    - red: the record named the branch `.invalid`, which the HEAD file holds under reftable;
      the branch is now asked of git
  - found by the story 2 review: an unborn branch → recorded with `head` null
    - red: an assertion error on the missing HEAD
  - found by the story 2 review: a held ref lock → reported as such, not as five lost races
    - red: `Regex pattern did not match … kept moving: 5 attempts lost the race`
  - found by the story 2 review: a wildcard-free glob (`tests`, `src`) → classified as the audit
    classifies it, not as a directory prefix
    - red: `assert (2, …) == (0, '')`
  - found by the story 2 review: a path matching both globs → named once, as a test
    - passed on its first run; listing every path in both groups, on purpose, failed it
  - found by the story 2 review: a code-only call, then a test-only call → exit 0 (the change is
    against the previous record, not HEAD)
    - passed on its first run; diffing against HEAD, on purpose, failed it
  - found by the story 2 review: a lost race → the change judged against the record that won
    - red: `assert (2, …) == (0, '')`
  - found by the story 2 review: a call whose record failed after its add → its change shown by
    the next call
    - passed on its first run; reading the change against an index kept between calls, on
      purpose, failed it
  - found by the second story 2 review: each snapshot follows the real index as it is at that
    call — a file it stopped tracking and now ignores, a flag it cleared (research R2)
    - red, against the index kept between calls that the first review's fixes had added:
      `assert 'conf.env' in {…}`; the copy per call restored
  - found by the second story 2 review: a file-system error (no space for the temporary index)
    → exit 2 with the error, not a traceback
    - red: failed before the catch existed
  - found by the second story 2 review: a worktree path holding a newline → exit 2 naming it
    - red: failed before the check existed (the reviewer saw `ValueError: too many values to
      unpack`)
  - cost, after both reviews: one `diff-index` over both globs and one `rev-parse` for the
    worktree: 91–92 ms on the benchmark, 91–94 ms on renta once git has rewritten its index,
    232 ms on a fresh clone until then (research L7, "Kept index")
- [X] T022 [US2] The `Stop` entry point `cli.py audit --stop` in `scripts/python/audit.py`: exit 0 when
  not installed, detached, on the default branch, or `stop_hook_active`; snapshot (`tool` =
  `Stop`); audit within `--budget` (default 120 s) with a 60 s deadline per run and no new run
  after the budget; exit 2 listing new tests whose failing verdict is final before the end, else
  exit 0 (contracts/ledger-hook.md "Stop"; FR-024)
  - a turn with a born-with-code test → exit 2, test, verdict, record and call named
    - red: argparse rejected `--stop` (usage, not behaviour); with the flag stubbed,
      `assert 1 == 2`
  - the same input with `stop_hook_active` true → exit 0
    - passed on its first run (the Stop entry came whole); ignoring the flag on purpose failed it
  - a turn ending on a red case in progress (`still-red`) → exit 0
    - passed on its first run; blocking on `still-red` on purpose failed it
  - `unobserved`, `never-run`, `not-judged` only → exit 0
    - passed on its first run; blocking on every failing verdict on purpose failed it
  - budget exhausted → no run started after it; exit 0, no output
    - passed on its first run; ignoring the budget on purpose failed it (a run was made)
  - the next turn → judges them from the memo
    - passed on its first run (the memo of T011): the second stop made no new run
  - one turn's test and code → judged within 30 seconds (SC-004)
    - measured end to end with real pytest: 1 s
  - a malformed configuration or no resolvable base → exit 2 with the error, once per turn
    - both passed on their first run; a configuration refusal that lets a stop through, on
      purpose, failed the first; on the default branch a stop goes through (blocking there on
      purpose failed that case)
    - the end-to-end hang check could not see a survivor (its marker was in the test file, not
      on a command line); it now reads the replay's process id; a replay without the
      process-group kill, on purpose, failed it
  - found by the second story 2 review: a git error in a plain `audit` → exit 2 with git's
    message
    - passed on its first run; removing the catch, on purpose, failed it
  - found by the story 2 review: a git error during the audit → exit 2 with git's message, no
    traceback
    - red: the error escaped as a traceback
  - found by the story 2 review: born-green, rewritten-to-green → exit 2 naming the test
    - passed on their first run; dropping each from the final set, on purpose, failed each
  - found by the story 2 review: a spent budget → still judged from runs already made
    - passed on its first run; ignoring the memo under a budget, on purpose, failed it
  - found by the story 2 review: the block lists only failing tests, the summary counts every new
    test
    - red: `'audit: 1 new tests: born-with-code 1; FAIL' == 'audit: 2 new tests: …, red 1; FAIL'`
  - found by the story 2 review: the Stop's record carries the payload's `session_id`
    - red: `('Stop', 'Stop') == ('Stop', 's')`
  - found by the story 2 review: detached, not installed, no ledger, not a git worktree → exit 0,
    no output
    - passed on their first run; making each refusal block, on purpose, failed each
  - found by the story 2 review: defaults of 60 s per run and 120 s in all
    - passed on its first run; a 300 s deadline and a 240 s budget, on purpose, each failed it
  - these cases end to end in `tests/audit.sh`, T021's in `tests/ledger.sh`

---

## Phase 5: User Story 3 — The implement workflow runs on observed evidence (P2)

**Goal**: projects get the ledger installed and the workflow running on the audit.

**Independent test**: compose the preset into a scratch Spec Kit project; the composed
`speckit-implement` carries each instruction; installing from it records.

- [X] T023 [US3] `cli.py install` in `scripts/python/install.py` (research R16): write `.specify/test-first.json` and both hook
  entries (`PostToolUse` matcher `*`; `Stop` with `timeout` 300, in seconds) into
  `.claude/settings.json`, creating it when absent, keeping every other entry, and commit exactly
  those two files as one commit; refuse with exit 1, the repository unchanged, on each condition of
  contracts/install-ledger.md (FR-013; FR-014; constitution IV)
  - a clean repository with tracked tests → one commit, two files, both entries, config as given
    - red: `NotImplementedError` from the stub
  - an existing `hooks.Stop` entry (the 1.x Stop gate) → kept, the new one added beside it
    - red: `KeyError: 'permissions'`
  - not at the root with `.specify/` → refused
    - red: `FileNotFoundError` writing `.specify/test-first.json`, from a subdirectory and from a
      root without `.specify/`
  - detached HEAD → refused; HEAD on the default branch → refused; no base resolves → refused
    - red: all three failed before the check existed
  - something staged → refused
    - red: `assert 0 == 1`
  - no `.claude/settings.json` → created, in the commit
    - pinned by the first case, whose project has no `.claude/` (its red above)
  - `.claude/settings.json` untracked, tracked with uncommitted changes, ignored, not a regular
    file, or skip-worktree → refused
    - red: all seven failed (untracked, changed, ignored, a directory, a symlink, skip-worktree,
      assume-unchanged)
  - a ledger entry already present → refused
    - red: `assert 0 == 1`; then the unchanged-repository check caught the configuration written
      before the refusal (`?? .specify/test-first.json`): every check now runs before any write
  - `--run` without `{file}` or `{junit}` → refused; a missing flag → refused
    - red: all six failed (argparse's own exit, or no refusal); the configuration is checked by
      `ledger.parse_config`, the hook's own validation
  - test globs matching no tracked file → refused
    - red: both failed (`spec/**`, and `tests`, which names a directory, not a glob)
  - a commit hook rejecting the commit → refused, working tree and index as before
    - red: `CalledProcessError` from `git commit`, with `settings.json` absent and committed
  - after every refusal → `git status`, the index and HEAD unchanged; these cases as pytest units
    over scratch repositories (`tests/python/test_install.py`), and an install and a refusal end
    to end through `cli.py` in `tests/install-ledger.sh` (quickstart step 3), a step of the CI
    `compose` job (T003)
  - found during implementation: `.specify/test-first.json` untracked or ignored → refused
    - red: both failed
  - found during implementation: a `settings.json` that is empty, not JSON, not an object, or with
    hooks of the wrong shape → refused
    - red: all five failed; then a hook entry that is not an object (`["x"]`) raised
      `AttributeError`
  - found during implementation: a git error while committing (a held `index.lock`) → refused,
    everything as before
    - red: `CalledProcessError` from `git add`
  - found during implementation (FR-011, constitution IV): the audit without the preset's
    `run-bounded.sh` → refused naming it, not "the command wrote no JUnit"
    - red: `assert 1 == 2`
  - found by T034's validation in renta: the install records the worktree as the ledger's origin
    — otherwise the first tool call's record is the origin and the test it writes is
    `unobserved` instead of `red` (observed: `audit: 2 new tests: born-with-code 1, unobserved 1`)
    - red: `CalledProcessError` from `git rev-list refs/worktree/test-first/ledger` (no ledger);
      `tests/install-ledger.sh` without its earlier workaround (an origin call) fails when the
      origin record is removed on purpose
  - found by T034's validation in renta: a test whose file did not load until its code existed
    is `born-with-code` with a reason saying so and the redo with a stub — the agent in the
    session saw an import error, took it for red, and suspected a false positive
    - red: `assert 'did not load' in ''`
  - found by the story 3 review: a glob git cannot use as a pathspec (`/src/**`, `../x/**`) →
    refused naming it, instead of every later hook call failing
    - red: both installed (`assert 0 == 1`)
  - found by the story 3 review: a symlinked `.claude/` → refused before anything is written
    - red: refused only after writing through the link, by git (`beyond a symbolic link`)
  - found by the story 3 review: terminated during its commit (SIGTERM) → everything as before
    - red: the two files left staged; removing the signal handler on purpose fails it again
  - found by the story 3 review: a hook entry whose `command` is not a string → refused
    - red: `TypeError` in `_installed`; a matcher that is not an object was already refused (the
      case now pins it)
  - found during implementation (constitution IV): `cli.py` writes no `__pycache__` beside the
    installed scripts
    - red: `tests/install-ledger.sh`: "a refusal changed the repository" (an untracked
      `__pycache__/`); removing the fix on purpose fails it again
- [X] T024 [US3] Rewrite `commands/speckit.implement.md` — Test-first, Stop gate and Independent
  review sections — for observed evidence: install the ledger before the first task, deriving
  `--tests`, `--sources` and `--run` from the plan and saying so when it cannot (FR-015); each case
  written and run in a call that changes no source, the code in a later call, tests renamed or
  consolidated in calls of their own, commits in calls of their own, code-writing subagents in this
  worktree one at a time (FR-016); no recorded red runs and no break-on-purpose route (FR-017);
  the audit at each story's close before the review, its report to the reviewer, the redo
  sequence and the `not-judged` remedies (FR-018); the reviewer uses the project's mutation check
  where its constitution or CI names one, else hand-written wrong versions (FR-019); a `tasks.md`
  from 1.x read with its red bullets kept and not required of new cases (FR-021); each rule
  overridden in core named (constitution I)
  - found by the story 3 review: the uv recipe for a packaged project (src layout) → `red`, with
    `PYTHONPATH=src` ahead of the editable install
    - red: `born-green tests.test_f::test_f` without it (`tests/audit.sh`, packaged scenario)
  - found by the story 3 review: renames in a call that changes only test-side paths, as the
    audit's refactor rule judges; the narrowed core rule "parallel tasks [P] can run together"
    named, and grepped in core with the "Tests" phase; compose checks the FR-016 and FR-018
    instructions
    - red: `speckit-implement no longer says: changes only test-side paths`, against HEAD
  - checked by T025's compose checks; red against the 1.x fragment: no `cli.py install`, no
    `cli.py audit`, and "Record the red run" and "Break the code it pins on purpose" still there
  - found during implementation: the `--run` examples measured in a scratch worktree — uv needs
    `UV_PROJECT_ENVIRONMENT={root}/.venv` (without it: `No module named pytest`), Node needs the
    real worktree's `node_modules` linked in (without it the Vitest scenario reports
    `not-judged`); contracts/configuration.md's example corrected (research L7, "Replay
    environments")
- [X] T025 [US3] Extend `tests/compose.sh`: the composed `speckit-implement` names
  `cli.py install` and `cli.py audit` at their installed path and the four Python modules are
  installed;
  the overridden core rules are still in core; the composed skill no longer asks for recorded red
  runs nor offers breaking the code on purpose (constitution I, II)
- [X] T026 [US3] Declare the new scripts in `preset.yml` (`cli`, `ledger`, `audit`, `install`) and
  check in `tests/compose.sh` that `specify preset info` lists them
  - red: `specify preset info does not list the … script` for the four, and for `run-bounded`,
    which 1.x ran from the fragment without declaring it; both now declared, and the implement
    template's description, which still said "each red run recorded", rewritten

---

## Phase 6: User Story 4 — Invariants get property cases (P3)

**Goal**: a stated invariant gets a property case in its implementing task's list.

**Independent test**: the composed `speckit-tasks` carries the instruction.

- [X] T027 [US4] Add to `commands/speckit.tasks.md`: when the spec states an invariant over a
  domain (an amount conserved, an order preserved, a bound), the implementing task's test list
  includes a property case over generated inputs naming the invariant, and only then (FR-020;
  research R9)
- [X] T028 [US4] Extend `tests/compose.sh`: the composed `speckit-tasks` carries the property-case
  instruction
  - red: `speckit-tasks does not add a property case for a stated invariant`, against the
    fragment before T027

---

## Phase 7: User Story 5 — Projects on 1.x move to 2.0.0 (P3)

**Goal**: a 1.6.0 project updates and keeps working.

**Independent test**: install 1.6.0 into a scratch project, update to HEAD's archive; the Stop
gate still runs and an old `tasks.md` is read.

- [X] T029 [US5] A migration check in `tests/compose.sh`: install the `v1.6.0` tag's archive with
  the real CLI, install its Stop gate, update to HEAD's archive; the gate still runs from
  `.claude/hooks/stop-gate.sh` and the composed skills still carry the 1.x `tasks.md` reading rule
  (FR-021; SC-005)
  - red: `the update did not install this version`, before T030 set 2.0.0; the gate's and the
    tasks.md checks passed against HEAD's fragment from the start
- [X] T030 [US5] Set `version: "2.0.0"` and the new descriptions in `preset.yml`; write the
  CHANGELOG 2.0.0 entry (Keep a Changelog: Added, Changed, Removed — the recorded red runs and the
  break-on-purpose route — with the migration steps) (FR-021; constitution V)

---

## Phase 8: Polish & cross-cutting

- [X] T031 README: the observed test-first section — what is recorded and audited, the
  verdicts, the Stop behaviour; the evidence of each added, changed or removed rule with its
  sources and dated measurements and tool versions (research R0–R14, L7); the limits section
  required by FR-022 and constitution VI; the migration notes (FR-021; FR-023)
  - found during implementation: the limits list carries the hook's cost on a clone whose index
    git has not rewritten since checkout — 232 ms per call on renta until any `git status` or
    commit (research L7, "Kept index") — and the Node recipe for `--run`, which links the real
    worktree's `node_modules` into the scratch worktree (tests/audit.sh, Vitest scenario)
- [X] T032 [P] Write `docs/decisions/0001-order-not-strength.md`,
  `0002-runner-agnostic-through-junit.md`, `0003-gates-block-once-per-turn.md` in MADR's shape,
  each linking its research entry (plan, "Decisions that outlive the feature")
- [X] T033 Update `CLAUDE.md`: the commands (`uv run ruff check`, `uv run mypy`, `uv run pytest`,
  `tests/ledger.sh`, `tests/install-ledger.sh`, `tests/audit.sh`), `scripts/python/` and
  `docs/decisions/` in "Where things live", and a pointer to `docs/decisions/`
- [X] T034 Validate in renta (quickstart step 7): install with its configuration, one test-only
  call and one mixed call, end the turn, run the audit; record the verdicts and a timed snapshot
  with the versions of Claude Code, git and pytest, dated, in the README (SC-003; SC-006;
  constitution III)
- [X] T035 Run the whole quickstart and every suite (`uv run ruff check`, `uv run mypy`,
  `uv run pytest`, `tests/ledger.sh`, `tests/install-ledger.sh`, `tests/audit.sh`,
  `tests/stop-gate.sh`, `tests/run-bounded.sh`, then commit and `tests/compose.sh`); all green
  - found by the polish review: the migration check needs the v1.6.0 tag, which CI's default
    shallow checkout lacks — `fetch-depth: 0` (a shallow, tagless clone failed with
    `not a valid object name: v1.6.0`; full history holds the tag)
  - found by the polish review: on a python3 older than 3.11, a stop that continues a blocked
    turn goes through
    - red: `cli.py audit --stop under Python 3.9, a continued stop: exit 2` (`tests/ledger.sh`)
  - found by the polish review: a ledger origin that fails after the commit says the commit
    stands and what the missing origin means
    - red: `assert 'first tool call' in "…first record failed: disk full"`
  - found by the polish review: a property case is taken with its task's first case, against a
    stub that raises; compose checks it, FR-020's "only then", and the 2.0 half of the 1.x
    tasks.md rule
    - red: `speckit-tasks no longer says: listed with the task's first case`, against HEAD
  - found by the polish review: `tests/audit.sh` runs the uv and Vitest recipes as the fragment
    gives them, and fails when the README's differ; npm where pnpm is missing
    - red: `the README's recipe differs from: PYTHONPATH=src …`, with the README's broken on purpose

---

## Dependencies & execution order

- Setup (T001–T003) → Foundational (T004–T008) → US1 (T009–T020) → US2 (T021–T022) → US3
  (T023–T026) → US4 (T027–T028) → US5 (T029–T030) → Polish (T031–T035).
- US2 needs US1's audit for the Stop entry; US3 needs US1 and US2 (the fragment runs both);
  US4 is independent of US1–US3 and can be taken any time after Setup; US5 needs US3.
- Within a story, tasks are sequential, simplest first.

## Parallel opportunities

- T002 and T003 touch different files once T001 lands.
- US4 (T027–T028) can run alongside US1–US3: it touches only `commands/speckit.tasks.md` and its
  compose check.
- T032 can be written alongside T031.

## Implementation strategy

- MVP: Setup, Foundational and US1 — the ledger records and the audit judges, run by hand. That
  alone turns L1's defect into a failing verdict.
- Then US2 (immediate feedback and the per-turn gate), US3 (projects get it through
  `/speckit-implement`), US4, US5, and the release polish.
- Each story closes with its independent review, as the implement fragment prescribes.

## Phase 9: Convergence

- [X] T036 CRITICAL: export-ignore `.gitignore` in `.gitattributes` and add it to the `for own in …` list of `tests/compose.sh`, seeing compose fail first (the archive installs `.specify/presets/test-first/.gitignore`) per Constitution V (contradicts)
  - red: `the installed preset carries this repository's .gitignore`
- [X] T037 Catch `OSError` in `audit.main` and `audit._stop` like a git error — exit 2 with the message, the Stop blocking once — with unit cases for a read-only memo and a failing temporary directory, seen failing first (exit 1 and a traceback today) per FR-024 (partial)
  - red: all three failed (the Stop with a read-only memo and with no temporary directory, the
    plain audit with no temporary directory)
- [X] T038 Add to the README's limits that once any Stop hook has blocked a turn its later stops skip the audit, and that a hook killed mid-run puts its call's changes under the next call's name per FR-022 (partial)
- [X] T039 Make the birth search, when every touching record is inconclusive, run the oldest touching record's previous as data-model.md says instead of the origin — or amend data-model.md to the origin, whichever the reasoning supports — with a unit case for the sequence that now gives `unobserved` per data-model "Finding a test's birth" (contradicts)
  - the code follows the data model: the origin keeps no information the record before the oldest
    touching one lacks, and a load that code made possible is lost by running the origin
  - red: `assert None == 3`
- [X] T040 Add end to end, or correct quickstart steps 2 and 5 and T008/T022 to say the units cover them: an unchanged tree adds no record, a linked worktree's own ledger, a subagent's id, branch and HEAD in a record (`tests/ledger.sh`); a turn ending on a red case is not blocked (`tests/audit.sh`) per quickstart steps 2 and 5 (partial)
  - added end to end; each passed on its first run (the units already pinned them): recording
    unchanged trees, dropping the agent id and blocking on `still-red`, on purpose, failed them
- [X] T041 Point the CHANGELOG 2.0.0 entry and constitution III's Check at the README's "Why 2.0.0's rules" / "Why 1.x's rules" sections (the "Why this shape" heading no longer exists; the constitution edit as a PATCH amendment) per Constitution III (contradicts)
- [X] T042 Correct tasks.md's `scripts/bash/` (installer, runner) line, make the R-ranges R0–R16 in plan.md and research.md, and move R16 above research.md's Landscape heading per research R16 (contradicts)
- [X] T043 Document the file-level `not-judged` entry (a test file whose runs never said which tests it holds) in data-model.md "Verdict", contracts/audit.md's output and the README per data-model "Verdict" (missing)
- [X] T044 Reword the README's `refactored` line to "a call that did not change test-side paths together with anything else" per FR-009 (contradicts)
- [X] T045 Remove the unused `WORKTREE_AND_INDEX` from `scripts/python/ledger.py` per plan: no code without a caller (unrequested)
- [ ] T046 After the pull request merges on green, tag `v2.0.0` on the merged commit and check that `preset.yml`, the CHANGELOG and the tag agree per Constitution V (missing)

## Phase 10: Convergence

- [X] T047 Turn a git failure while resolving the base (`merge-base` with no common ancestor, an unresolvable `--base`) into a refusal carrying git's message, so `audit` exits 2 and `audit --stop` blocks once, with unit cases for an orphan branch and a bad `--base` seen failing first (a traceback, exit 1, today) per FR-024 (partial)
  - red: all three failed (a bad `--base`, an orphan branch for the audit and for the Stop)
- [ ] T048 Treat a memo entry that cannot be read as JSON as a miss — run again and rewrite it — instead of an uncaught `ValueError` that ends the Stop unblocked, with a unit case seen failing first per FR-024 (partial)
- [ ] T049 Run the installer's `git commit`, which runs the project's commit hooks, under `run-bounded.sh` with a deadline, a hook that outlives it being refused with everything put back, with a unit case seen failing first per Constitution IV (contradicts)
- [ ] T050 Correct the README's scenario count for `tests/audit.sh` to what the suite holds (36 with real pytest, one with Vitest) per Constitution VI (contradicts)
