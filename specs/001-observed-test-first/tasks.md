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
`scripts/bash/` (installer, runner), `tests/python/` (pytest units), `tests/*.sh` (end-to-end
suites in scratch repositories), `commands/` (fragments).

---

## Phase 1: Setup

- [X] T001 Add the Python toolchain as its own change: `pyproject.toml` with a uv dev group
  (ruff, mypy, pytest, pytest-timeout), `[tool.uv] package = false`, `requires-python = ">=3.10"`,
  mypy strict with `python_version = "3.10"` over `scripts/python` and `tests/python`, ruff
  `target-version = "py310"`, pytest `timeout` set and `testpaths = ["tests/python"]`; `uv.lock`
  committed. The 3.10 floor because the scripts run on other projects' `python3` (plan, Technical
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
  `uv run pytest` (also under Python 3.10, `uv run --python 3.10 pytest`), `tests/ledger.sh`,
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
  - `stopped: possible spec gap` — whether `**/test_*.py` matches a root-level `test_x.py`
    (found during implementation): plain `fnmatch` says no, gitignore-style globs say yes; the
    data model says only "`fnmatch`, where `**` matches across directories"
- [ ] T006 Snapshot the worktree as a tree in `scripts/python/ledger.py`: temporary index seeded
  from the worktree's own, `git add -A`, `git write-tree`; tracked and untracked-but-not-ignored
  files; the real index and the worktree never modified (research R2; FR-001; constitution IV)
  - a clean repository → the HEAD commit's tree
  - an untracked file → in the tree; an ignored one → not
  - a deleted tracked file → absent from the tree
  - staged and unstaged edits of one file → the worktree's content
  - after the snapshot, `git status --porcelain` and `.git/index` byte-identical to before
- [ ] T007 Append a record in `scripts/python/ledger.py`: `git commit-tree <tree> -p <previous>`
  with the message JSON `time`, `session`, `agent`, `tool`, `call`, `branch`, `head`; move
  `refs/worktree/test-first/ledger` with `git update-ref <ref> <new> <old>`, retried on a race;
  no record when the tree equals the newest record's (data-model "Record"; FR-002; FR-003)
  - first snapshot of a worktree → one record, no parent
  - same tree again → no new record
  - a changed tree → a record whose parent is the previous newest
  - message JSON carries all seven fields; `agent` null without `agent_id`; `branch` null when
    detached
  - a concurrent update between read and write → retried, both records in the chain
  - a linked worktree → its own ref, the main worktree's chain untouched
  - `git gc --prune=now` → every record still reachable
- [ ] T008 The `PostToolUse` entry point of `scripts/python/ledger.py`: read the hook JSON from
  stdin (`cwd`, `session_id`, `agent_id`, `tool_name`, `tool_use_id`), resolve the worktree of
  `cwd`, snapshot and append; exit 0 silently when not in a git worktree or not installed; exit 2
  with the error on stderr when recording fails (contracts/ledger-hook.md steps 1–3 and failures;
  FR-001; FR-004)
  - `cwd` outside any git repository → exit 0, no output
  - a repository without `.specify/test-first.json` → exit 0, no output
  - installed, a changed file → exit 0, one record with the input's session, tool and call
  - a subagent's input with `agent_id` → the record carries it
  - `cwd` in a subdirectory or a linked worktree → that worktree's ledger
  - a malformed configuration → exit 2, stderr names it, no record
  - git unable to write (objects directory read-only) → exit 2, stderr has git's error, worktree
    and real index unchanged
  - a source and a test written by one Bash heredoc → one record holding both
  - one snapshot of a ~1,000-file scratch repository → under 100 ms, median of five (SC-003)
  - these cases end to end, with recorded hook inputs in scratch repositories, in `tests/ledger.sh`
    (quickstart step 2), added as a step of the CI `compose` job (T003)

---

## Phase 3: User Story 1 — A test written together with its code is caught (P1) 🎯 MVP

**Goal**: the audit judges every new test from the ledger and replays, and fails on code-first.

**Independent test**: in a scratch pytest repository with the ledger recording, replay "test then
code" and "test and code in one shell call"; the audit reports `red` and exits 0 for the first,
`born-with-code` and exits 1 for the second.

- [ ] T009 [US1] Parse one JUnit XML file into test outcomes in `scripts/python/audit.py`
  (data-model "Run"; research R6; FR-008)
  - no file written → "no JUnit"
  - `tests="0"` and no `testcase` → conclusive, no tests
  - one `testcase` without children → passed, id `classname::name`
  - a `failure` child → failed; an `error` child → failed; a `skipped` child → skipped
  - pytest's `<skipped type="pytest.xfail">` → skipped
  - nested `testsuite` elements (Vitest, Jest) → every `testcase` found
  - malformed XML → "no JUnit" (treated as a run that wrote none)
- [ ] T010 [US1] Run one test file in a scratch worktree in `scripts/python/audit.py`: one
  detached scratch worktree in a temporary directory, `git read-tree -u --reset <tree>`,
  `git clean -fdx`, the configured command through `sh -c` and
  `scripts/bash/run-bounded.sh <deadline>`, `{file}`, `{junit}` and `{root}` substituted and
  shell-quoted; stale scratch worktrees of an earlier killed audit pruned at start; removed on exit
  (research R7; FR-011; constitution IV)
  - a passing test file → its outcomes; the command ran with the scratch worktree as cwd
  - a file name with a space and a quote → substituted safely
  - a command that hangs → stopped at the deadline with its process group; "timed out"
  - an untracked cache from a previous run (`__pycache__`) → gone before the next run
  - `{root}` → the real worktree's absolute path
  - after the audit, `git worktree list` shows only the real worktrees; after a killed audit and a
    rerun, the same
- [ ] T011 [US1] Memoize runs in `scripts/python/audit.py` under
  `git rev-parse --git-path test-first/runs`, keyed by (tree id, file, hash of `run`) (data-model
  "Run", Memo; FR-026)
  - the same key twice → the command runs once
  - a different `run` string → runs again
  - a run that wrote no JUnit → not stored; runs again next time
  - a timed-out run stored with its deadline → not retried under the same or a shorter deadline;
    retried under a longer one
  - the memo directory deleted → the next audit gives the same verdicts
- [ ] T012 [US1] Build the replay trees in `scripts/python/audit.py` with git plumbing, without
  touching the real index: before-version of *g*, base overlay of *r*, no-sources of *r*, and the
  load probe's tree (data-model "Run", variants; research R5; FR-028)
  - before-version → every test-side path from *g*'s previous, every other path from *g*
  - base overlay → every test-side path from *r*, every other path from the base, a path the base
    lacks removed
  - a template outside `sources` changed at *r* → the base overlay has the base's template
  - no-sources → every `sources` path removed, configuration files kept
  - load probe → the file's content replaced by bytes no language parses, nothing else changed
- [ ] T013 [US1] Decide whether a run is inconclusive in `scripts/python/audit.py`: no JUnit, or
  every case failed and the load probe on the same tree and file reports exactly the same ids; the
  probe runs only when every case failed (data-model "Run"; research R6; FR-007)
  - a run with one passing case → conclusive, no probe
  - zero cases → conclusive
  - pytest collection failure (`classname=""`, `name=<module>`, error) and a probe with the same
    case → inconclusive
  - Vitest's file-named failure and a probe with the same case → inconclusive (skip when node is
    unavailable, and say so)
  - every test genuinely failing by assertion → the probe reports a different id set → conclusive
- [ ] T014 [US1] Resolve the base in `scripts/python/audit.py`: merge base with the
  remote-tracking default (`origin/HEAD`, else `origin/main`, else `origin/master`); without an
  `origin` remote, the local `init.defaultBranch`, `main`, `master`; refuse when none resolves or
  HEAD is on the default branch; no network (data-model "Base"; research R14; FR-027)
  - `origin/HEAD` → `origin/main` → its merge base with HEAD
  - `origin` without `origin/HEAD` but with `origin/main` → that
  - no remote, local `main` → its merge base
  - a local merge into `main` after the branch's commits → base unchanged when `origin/main` exists
  - HEAD on `main` → refusal naming it
  - nothing resolves → refusal naming what was tried
  - `--base <rev>` → that commit
  - an `origin` whose URL is unreachable → the base resolves from local refs; no fetch is made
- [ ] T015 [US1] Compute the effective history of the current branch from the ledger in
  `scripts/python/audit.py`, and each record's previous and change (data-model "Effective
  history")
  - one branch, five records → all five, each previous the one before
  - a visit to another branch and back → the visit's records skipped; the return compared with
    the branch's last record
  - `git checkout -b feat` with uncommitted work → the records before it, on the original branch,
    included; the new branch's first change compared with them
  - a branch renamed mid-line → one continuous line
  - a rebase (detached records in between) → detached records skipped
  - the origin → no previous
- [ ] T016 [US1] Find a test's birth in `scripts/python/audit.py`: walk back over the records
  that touched its file, running the record before each; skip touching records whose run is
  inconclusive; scan forward when it appeared without its file changing; no birth back to the
  origin; imported when its birth record's HEAD moved to a commit already holding it; restored
  when its file is identical to an earlier accepted state (data-model "Finding a test's birth",
  "Restored", "Imported"; FR-007)
  - a test in a new file → born at the call that created the file
  - a test added to a file written 300 records earlier → born at the adding call, with one extra
    run
  - a file broken by a typo for one call, then fixed → born where first written, not at the fix
  - a file that cannot load until a stub is written by a source-only call → born at the stub's
    record
  - present back to the origin → no birth
  - removed and written again (the redo sequence) → born at the rewrite
  - `git stash` then `git stash pop` in another call → restored with its earlier verdict
  - a test written and committed in one call → imported
  - a test brought by `git merge` or `git pull` → imported
- [ ] T017 [US1] Follow a test from its birth in `scripts/python/audit.py`: run its file at every
  record of the effective history until its first run that is not skipped, and, when that failed,
  until it passes; then the green check on the before-version (data-model "Test lifecycle"; FR-009)
  - test, red, then a source-only call → `red`
  - a red test whose expected value is changed in the same call as the code → `rewritten-to-green`
  - a red test made to pass by changing only a test helper → `rewritten-to-green`
  - a red test with a missing method that a later source call adds → `red` (scenario 6)
  - the crash the test reproduces, then the fix → `red`
  - one call changing an API and a shared fixture, so the before-version does not load →
    `not-judged`, reason and remedy named
  - skipped at birth, unskipped and red later, then code → `red`
  - still failing at the newest record → `still-red`; only skipped → `never-run`
- [ ] T018 [US1] Judge a test whose first run passed in `scripts/python/audit.py`: steps 1–4 in
  order — no-sources pass, base-overlay pass, the refactor count in a call that is not two-sided,
  then by source in the change (data-model "Judged at first run"; research R7, R13; FR-009;
  FR-025)
  - test and code in one shell call → `born-with-code`, call named
  - code first, then the test alone → `born-green`
  - a test moved from a file at the base, passing against the base → `predates`
  - a test that imports nothing from `sources` → `born-green`, reason "passes without sources"
  - an environment that imports the real worktree's code → a would-be `predates` is `born-green`
    with that reason
  - a test-only call renaming one accepted test → `refactored`, listing it
  - three accepted tests merged into one parametrized test with three ids → `refactored`
  - a rename plus one more passing test in the same call → none refactored
  - a rename, a new case and its code in one mixed call → `born-with-code`
  - an enum member renamed in code, renaming one parametrized id → `refactored`
  - behaviour first written in a template outside `sources`, tested later → `born-green`
- [ ] T019 [US1] Determine the new tests and assemble the verdicts in `scripts/python/audit.py`:
  tests reported at the newest record by test files that differ from the base and absent from the
  base's runs; a file inconclusive at the newest record → its last conclusive tests `not-judged`;
  a dependent run past its deadline → `not-judged`; a test deleted before the end → not judged
  (data-model "Verdict"; FR-006; FR-010)
  - a new test in a changed file → judged; an existing test changed in the feature → not new
  - a test deleted before the end → absent from the report
  - a test file broken at the newest record → its tests `not-judged`, exit 1
  - a hanging replay → `not-judged`, exit 1, nothing left running
  - every test `red`, `predates`, `refactored` or `never-run` → exit 0, never-run listed
  - any other verdict → exit 1
- [ ] T020 [US1] The audit's command line in `scripts/python/audit.py`: `--base`, `--deadline`;
  snapshot first when the worktree differs from the newest record (`tool` = `audit`); refuse with
  exit 2 on a detached HEAD, HEAD on the default branch, no ledger, no configuration or no base;
  stdout lines `<verdict> <test id> <record> <tool> <call>` (`-` for `unobserved`), reasons and
  replaced tests, each failing verdict's remedy, and the summary line (contracts/audit.md; FR-012;
  FR-026)
  - a worktree edited after the last call → a record with `tool` = `audit` before judging
  - no ledger → exit 2, message; detached HEAD → exit 2
  - a report → grouped by verdict, summary `audit: <n> new tests: …; pass|FAIL`
  - `born-with-code` → its line ends with the redo sequence
  - the audit reads no `tasks.md`: a `tasks.md` claiming red runs changes nothing
  - end to end in `tests/audit.sh`: ledgers built in a scratch pytest project by replaying recorded
    tool-call sequences through `ledger.py`, every case of quickstart step 4 and spec Story 1
    scenarios 1–12, verdicts and exit codes asserted (SC-001, SC-002), added as a step of the CI
    `compose` job (T003)
  - a second audit → reruns nothing (memo)
  - a 60-test, 20-file feature → warm under 2 minutes, cold time reported (SC-004)

**Checkpoint**: US1 delivers the guarantee; the audit can be run by hand.

---

## Phase 4: User Story 2 — The agent hears it at once (P2)

**Goal**: a mixed call is reported after the call; a final failing verdict blocks the turn once.

**Independent test**: with the ledger recording in a scratch repository, a call changing a test
and a source file returns the message; a test-only call returns none; ending the turn after a
born-with-code test is blocked once, and the next stop passes.

- [ ] T021 [US2] Report a mixed call in `scripts/python/ledger.py`: exit 2 with stderr naming the
  test paths and the source paths, saying that a test added or changed with the code that
  satisfies it will fail the audit, and the redo sequence (research R4; contracts/ledger-hook.md
  step 4; FR-005)
  - a call changing `tests/t.py` and `src/x.py` → exit 2, both named
  - only tests, only sources, or neither → exit 0, no output
  - tests and `README.md` → exit 0 (documentation is neither)
  - a symbol renamed across code and tests → exit 2, the message worded as conditional
- [ ] T022 [US2] The `Stop` entry point `audit.py --stop` in `scripts/python/audit.py`: exit 0 when
  not installed, detached, on the default branch, or `stop_hook_active`; snapshot (`tool` =
  `Stop`); audit within `--budget` (default 120 s) with a 60 s deadline per run and no new run
  after the budget; exit 2 listing new tests whose failing verdict is final before the end, else
  exit 0 (contracts/ledger-hook.md "Stop"; FR-024)
  - a turn with a born-with-code test → exit 2, test, verdict, record and call named
  - the same input with `stop_hook_active` true → exit 0
  - a turn ending on a red case in progress (`still-red`) → exit 0
  - `unobserved`, `never-run`, `not-judged` only → exit 0
  - budget exhausted → no run started after it; exit 0, no output
  - the next turn → judges them from the memo
  - one turn's test and code → judged within 30 seconds (SC-004)
  - a malformed configuration or no resolvable base → exit 2 with the error, once per turn
  - these cases end to end in `tests/audit.sh`, T021's in `tests/ledger.sh`

---

## Phase 5: User Story 3 — The implement workflow runs on observed evidence (P2)

**Goal**: projects get the ledger installed and the workflow running on the audit.

**Independent test**: compose the preset into a scratch Spec Kit project; the composed
`speckit-implement` carries each instruction; installing from it records.

- [ ] T023 [US3] `scripts/bash/install-ledger.sh`: write `.specify/test-first.json` and both hook
  entries (`PostToolUse` matcher `*`; `Stop` with `timeout` 300, in seconds) into
  `.claude/settings.json`, creating it when absent, keeping every other entry, and commit exactly
  those two files as one commit; refuse with exit 1, the repository unchanged, on each condition of
  contracts/install-ledger.md (FR-013; FR-014; constitution IV)
  - a clean repository with tracked tests → one commit, two files, both entries, config as given
  - an existing `hooks.Stop` entry (the 1.x Stop gate) → kept, the new one added beside it
  - not at the root with `.specify/` → refused
  - detached HEAD → refused; HEAD on the default branch → refused; no base resolves → refused
  - something staged → refused
  - no `.claude/settings.json` → created, in the commit
  - `.claude/settings.json` untracked, tracked with uncommitted changes, ignored, not a regular
    file, or skip-worktree → refused
  - a ledger entry already present → refused
  - `--run` without `{file}` or `{junit}` → refused; a missing flag → refused
  - test globs matching no tracked file → refused
  - no `jq` → refused
  - a commit hook rejecting the commit → refused, working tree and index as before
  - after every refusal → `git status`, the index and HEAD unchanged; these cases end to end in
    `tests/install-ledger.sh` (quickstart step 3), added as a step of the CI `compose` job (T003)
- [ ] T024 [US3] Rewrite `commands/speckit.implement.md` — Test-first, Stop gate and Independent
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
- [ ] T025 [US3] Extend `tests/compose.sh`: the composed `speckit-implement` names
  `install-ledger.sh` and `audit.py` at their installed paths and those files are installed;
  the overridden core rules are still in core; the composed skill no longer asks for recorded red
  runs nor offers breaking the code on purpose (constitution I, II)
- [ ] T026 [US3] Declare the new scripts in `preset.yml` (`install-ledger`, `ledger`, `audit`) and
  check in `tests/compose.sh` that `specify preset info` lists them

---

## Phase 6: User Story 4 — Invariants get property cases (P3)

**Goal**: a stated invariant gets a property case in its implementing task's list.

**Independent test**: the composed `speckit-tasks` carries the instruction.

- [ ] T027 [US4] Add to `commands/speckit.tasks.md`: when the spec states an invariant over a
  domain (an amount conserved, an order preserved, a bound), the implementing task's test list
  includes a property case over generated inputs naming the invariant, and only then (FR-020;
  research R9)
- [ ] T028 [US4] Extend `tests/compose.sh`: the composed `speckit-tasks` carries the property-case
  instruction

---

## Phase 7: User Story 5 — Projects on 1.x move to 2.0.0 (P3)

**Goal**: a 1.6.0 project updates and keeps working.

**Independent test**: install 1.6.0 into a scratch project, update to HEAD's archive; the Stop
gate still runs and an old `tasks.md` is read.

- [ ] T029 [US5] A migration check in `tests/compose.sh`: install the `v1.6.0` tag's archive with
  the real CLI, install its Stop gate, update to HEAD's archive; the gate still runs from
  `.claude/hooks/stop-gate.sh` and the composed skills still carry the 1.x `tasks.md` reading rule
  (FR-021; SC-005)
- [ ] T030 [US5] Set `version: "2.0.0"` and the new descriptions in `preset.yml`; write the
  CHANGELOG 2.0.0 entry (Keep a Changelog: Added, Changed, Removed — the recorded red runs and the
  break-on-purpose route — with the migration steps) (FR-021; constitution V)

---

## Phase 8: Polish & cross-cutting

- [ ] T031 README: the observed test-first section — what is recorded and audited, the
  verdicts, the Stop behaviour; the evidence of each added, changed or removed rule with its
  sources and dated measurements and tool versions (research R0–R14, L7); the limits section
  required by FR-022 and constitution VI; the migration notes (FR-021; FR-023)
- [ ] T032 [P] Write `docs/decisions/0001-order-not-strength.md`,
  `0002-runner-agnostic-through-junit.md`, `0003-gates-block-once-per-turn.md` in MADR's shape,
  each linking its research entry (plan, "Decisions that outlive the feature")
- [ ] T033 Update `CLAUDE.md`: the commands (`uv run ruff check`, `uv run mypy`, `uv run pytest`,
  `tests/ledger.sh`, `tests/install-ledger.sh`, `tests/audit.sh`), `scripts/python/` and
  `docs/decisions/` in "Where things live", and a pointer to `docs/decisions/`
- [ ] T034 Validate in renta (quickstart step 7): install with its configuration, one test-only
  call and one mixed call, end the turn, run the audit; record the verdicts and a timed snapshot
  with the versions of Claude Code, git and pytest, dated, in the README (SC-003; SC-006;
  constitution III)
- [ ] T035 Run the whole quickstart and every suite (`uv run ruff check`, `uv run mypy`,
  `uv run pytest`, `tests/ledger.sh`, `tests/install-ledger.sh`, `tests/audit.sh`,
  `tests/stop-gate.sh`, `tests/run-bounded.sh`, then commit and `tests/compose.sh`); all green

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
