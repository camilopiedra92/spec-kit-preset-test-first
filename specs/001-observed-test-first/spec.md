# Feature Specification: Observed test-first

**Feature Branch**: `observed-test-first`

**Created**: 2026-10-07

**Status**: Draft

**Input**: User description: "Observed test-first — make the order red-then-green observed by the
machine instead of reported by the agent." (the full description, evidence and scope were given in
the `/speckit-specify` invocation of 2026-10-07 and are summarised under Context)

## Context

A feature implemented with this preset at version 1.6.0 (renta, `001-bridge-adjudication`,
2026-10-06/07) recorded about 60 test cases, 27 of them as "passed on first run". In the session
transcript, 11 test runs each came from a single tool call — most often a shell command, not the
file-editing tool — that wrote the production code and its test together and ran green; the case
was then justified by breaking the code on purpose, as the 1.6.0 fragment allows ("A new test that
passes on its first run has not been watched failing. Break the code it pins on purpose..."). The
red runs recorded in `tasks.md` are written by the same agent that writes the code.

No spec-driven framework or agent tool surveyed on 2026-10-07 verifies the order from what happened:
Spec Kit core, Kiro, BMAD, obra/superpowers, OpenSpec, Gemini Conductor and cc-sdd prompt for
test-first, and the ones that check something check the agent's own report (pasted red output,
supplied counts, a commit message); TDD Guard and its successor Probity judge each write with a
language model. Fault detection is measured to depend on the test being written without the code in
view (arXiv 2607.05139: 25% of faults found against 14% when written after faulty code); observed
order is necessary for that, though not proof of it — a test can still be written after code drafted
elsewhere. The mechanical check that a test encodes new behaviour is SWE-bench's FAIL_TO_PASS: the
test fails before the change and passes after. This feature applies that check at the moment each
test was written and at the call that made it pass. It checks order, not strength: whether a test's
assertions tell right from wrong is measured by mutation testing at the story review.

## Clarifications

### Session 2026-10-07

- Q: Should a new test that passes the moment it first appears, in a call that changed no source
  file, fail the audit? → A: Yes, unless it also passes against the source at the base — then its
  behaviour predates the feature (a moved or characterization test) and it is accepted as such.
  Otherwise the code-first route stays open one call apart. The remedy is the redo sequence of
  Story 1, which makes the machine observe what "break it on purpose" only narrated.
- Revision after an independent review and a second landscape pass (research.md R0, R5, R12, R13):
  - A red is any run that did not pass — a failure or an error. JUnit cannot tell an assertion
    from an exception in pytest (measured), and a test whose exception *is* the bug is a valid red;
    strength is the mutation check's job.
  - A test that was red must pass, at the call that turned it green, in the version written before
    that call; otherwise it was rewritten to green.
  - A test that replaced accepted tests in a test-only call is refactored, not born green.
  - The audit also runs as a Stop hook, so each turn's verdicts reach the agent whether or not it
    runs the audit.
  - Births are found along the branch's own history, not a time range.
- Second revision after a review of the first (research.md R5, R6, R13, R14):
  - Replays swap the whole test side or the whole rest of the tree between records, so code
    written outside the source globs (a template, a schema) and test support files (helpers, case
    tables) are judged too.
  - A refactored test must be satisfied by the same code change that turned a test it replaced
    green (replaced in the third revision, below).
  - Whether a file failed to load is measured at each run by replacing it with garbage, because
    runners report it differently (pytest, Vitest).
  - Tests that arrive by a merge are judged on the merged branch's records in this worktree
    (replaced in the third revision, below).
- Third revision after a third review (research.md R13, R14): the edge rules that kept opening new
  holes were replaced by simple, fail-closed ones with stated limits:
  - A call may replace accepted tests with at most as many passing ones (a rename, a
    consolidation); more fail, and the rename is split from the new test.
  - A test that arrives with commits the ledger did not see written (a merge, a pull) is
    unobserved; the fragment keeps feature work on one branch in one worktree.
  - A test that never ran vouches for nothing and does not fail the audit; it is listed.
  - When the order cannot be told (an old fixture that no longer loads, a file broken at the end),
    the test is not judged and fails, with the remedy named.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A test written together with its code is caught (Priority: P1)

A project owner runs `/speckit-implement` with the preset. The agent writes code however it likes —
the file-editing tool, a shell heredoc, a script, a subagent. An audit reads what the repository
looked like after every tool call and, for every test that is new in the feature, replays that
test where it first appeared and where it first passed. Every new test must have been seen not
passing there, and the code that made it pass must satisfy the test as it was written before. A
test that passed where it first ran fails the audit — named as born with its code when that call
changed source — unless its behaviour predates the feature or it replaced accepted tests. The owner
and the story's reviewer read the audit, not the agent's account of its own red runs.

**Why this priority**: it is the defect observed. Without it every other part of the preset still
rests on the agent's self-report.

**Independent Test**: in a scratch repository with the ledger installed, replay two recorded
sequences of tool calls — test then code; test and code in one shell call — and run the audit: the
first is red, the second is born with its code and the audit exits non-zero.

**Acceptance Scenarios**:

1. **Given** a feature in which a test was added by one call and its code by a later one, **When**
   the audit runs, **Then** the test is reported as red and the audit passes.
2. **Given** a feature in which one shell call added a test and a source change, **When** the audit
   runs, **Then** the test is reported as born with its code, the call is named, and the audit
   fails.
3. **Given** a test added alone that passes at once because code written earlier in the feature
   already covers it, **When** the audit runs, **Then** it is reported as born green and the audit
   fails.
4. **Given** a test added alone that passes at once and also passes against the source at the
   base (a moved or characterization test), **When** the audit runs, **Then** it is reported as
   predating the feature and does not fail the audit.
5. **Given** a test whose file cannot load because the code it imports does not exist yet, and a
   later call adds a stub under which it fails, then the code, **When** the audit runs, **Then** it
   is red; **given** instead that the later call adds the full code and the test passes at once,
   **Then** it is born with its code.
6. **Given** a test that fails at first by an exception — a missing method, or the crash it was
   written to reproduce — and passes after a later call changes only source, **When** the audit
   runs, **Then** it is red.
7. **Given** a test born with its code that the agent then redid — removed the test, reverted the
   code, wrote the test again, saw it fail, restored the code — **When** the audit runs, **Then**
   the test's latest birth is the one judged, and it is red.
8. **Given** a test that failed at birth and was changed in the same call that changed the code
   and made it pass, so that its earlier version still fails against the new code, **When** the
   audit runs, **Then** it is reported as rewritten to green and the audit fails.
9. **Given** a test edited, in a call that changed no source, until it passes, **When** the audit
   runs, **Then** it is reported as rewritten to green and the audit fails.
10. **Given** a call that renames accepted tests or merges them into one parametrized test,
    **When** the audit runs, **Then** the new tests are reported as refactored, listed with the
    tests they replaced, and the audit passes; **given** that the same call also adds a test for
    code written earlier, so more passing tests appear than were replaced, **Then** none of them is
    refactored and the audit fails.
11. **Given** a red test whose expected value lives in a test helper, and a call that changes only
    that helper until the test passes, **When** the audit runs, **Then** the test is rewritten to
    green and the audit fails.
12. **Given** behaviour written first in a file outside the source globs (a template, a schema) and
    a test added for it later, **When** the audit runs, **Then** the test is born green, not
    predating the feature.

---

### User Story 2 - The agent hears it at once (Priority: P2)

When a single tool call changes test files and source files together, the agent is told
immediately after that call, with the files named, so it can redo the cycle while it is cheap. At
the end of each turn, a test already judged as written with or after its code blocks the turn
once, so the agent cannot finish without seeing it.

**Why this priority**: the audit at the story's close is the full report; these are what keep its
failures rare and what make its verdicts independent of the agent remembering to run it.

**Independent Test**: install the ledger in a scratch repository, simulate a tool call that changes
a test file and a source file, and read the message returned to the agent; simulate one that
changes only a test file and see no message; simulate the end of the turn and see it blocked once
with the test named.

**Acceptance Scenarios**:

1. **Given** the ledger installed, **When** a call changes a test file and a source file, **Then**
   the agent receives a message naming both groups of files.
2. **Given** the ledger installed, **When** a call changes only test files, only source files, or
   neither, **Then** the agent receives no message from the ledger.
3. **Given** a call that renames a symbol across code and tests without renaming any test (a
   refactor), **When** it completes, **Then** the message appears, but the audit does not fail on
   it, because no test was born or turned green in it.
4. **Given** a turn in which a test was born with its code, **When** the agent tries to end the
   turn, **Then** it is blocked once with the test, the verdict and the call named; the next stop
   of that turn goes through.
5. **Given** a turn that ends with a test still red (the case in progress), **When** the agent ends
   the turn, **Then** it is not blocked for it.

---

### User Story 3 - The implement workflow runs on observed evidence (Priority: P2)

The project owner's `/speckit-implement` installs the ledger before the first task; takes each case
as a test written and run in a call that touches no source file, then the code in a later call;
renames or consolidates tests in calls that touch no source file; closes each story with the audit
and then the independent review; and no longer asks the agent to record its own red runs or to
justify a first-run pass by breaking the code. Where the project has a mutation check — named by
its constitution or run by its CI — the story review uses it to measure the tests' strength;
otherwise the reviewer writes wrong versions by hand, as today.

**Why this priority**: it is how the ledger and the audit reach a project.

**Independent Test**: compose the preset into a scratch Spec Kit project and read the composed
`speckit-implement` skill for each instruction above; install from the composed instructions in a
scratch repository and see the ledger recording.

**Acceptance Scenarios**:

1. **Given** a project without the ledger, **When** `/speckit-implement` starts, **Then** the ledger
   is installed and committed before the first task, with the project's configuration.
2. **Given** a completed user story, **When** the story closes, **Then** the audit runs before the
   independent review and the review receives its report.
3. **Given** an audit that reports a test born with its code, born green or rewritten to green,
   **When** the agent remedies it, **Then** it follows the redo sequence of Story 1, scenario 7, and
   reruns the audit.
4. **Given** a project whose constitution or CI names a mutation check, **When** the story review
   runs, **Then** the reviewer runs that check over the story's changes and treats each surviving
   mutant as a test gap or justifies it.

---

### User Story 4 - Invariants get property cases (Priority: P3)

When the spec states an invariant over a domain — an amount conserved, an order preserved, a total
that never goes negative — `/speckit-tasks` adds a property case to the test list of the task that
implements it: a case stated over generated inputs rather than one example.

**Why this priority**: it widens what a test list catches where example cases are thin; it does not
depend on Stories 1–3.

**Independent Test**: compose the preset and read the composed `speckit-tasks` skill for the
instruction; run `/speckit-tasks` on a spec that states a conservation invariant and see a property
case in the relevant task's list.

**Acceptance Scenarios**:

1. **Given** a spec stating an invariant, **When** tasks are generated, **Then** the implementing
   task's list includes a property case that names the invariant.
2. **Given** a spec with no invariant, **When** tasks are generated, **Then** no property case is
   added.

---

### User Story 5 - Projects on 1.x move to 2.0.0 (Priority: P3)

A project that installed 1.x updates to 2.0.0 and keeps working: its existing `tasks.md`, with red
runs recorded as bullets, is still readable by `/speckit-implement`; its Stop gate keeps running;
the README and CHANGELOG say what changed and what to do.

**Why this priority**: needed for release, after the behaviour exists.

**Independent Test**: install 1.6.0 into a scratch project, update to the 2.0.0 archive, and check
that the gate still runs and the composed skills read an old `tasks.md`.

**Acceptance Scenarios**:

1. **Given** a project on 1.6.0 with a Stop gate, **When** it updates to 2.0.0, **Then** the gate
   still runs and the ledger is installed at the next `/speckit-implement`.
2. **Given** a `tasks.md` with recorded red bullets, **When** `/speckit-implement` reads it,
   **Then** the bullets are kept and not required of new cases.

---

### Edge Cases

- A new test has no birth in the ledger (the ledger was installed after the test was written, or
  its records were lost): the audit reports it as unobserved and fails; it never assumes a red it
  did not see.
- A test moved or renamed: refactored when its call changed only test-side paths and replaced at
  least as many accepted tests as it adds passing ones; predating the feature when it also passes
  against the base; otherwise born green, or born with its code when its call changed source. The
  fragment has tests renamed in calls of their own.
- A test id generated from code (a parametrized case named after an enum member) that changes
  because the code changed: refactored by the same count, within its file.
- A test added to an unchanged test file by a change elsewhere (a row in a case table kept in
  another file): not found as new — a stated limit (FR-022).
- The body of a test that is already accepted is changed to cover new code: not judged — identity is
  the test's name. The story review's mutation check is what measures that test (FR-022).
- The redo sequence removes a test that is the only one in its file: the file is removed, because
  some runners (Vitest) report a file without tests the same way as a file that cannot load.
- A test that existed at the base and is changed in the feature: it is not new and is not judged
  by birth; only tests absent at the base are.
- A test new in the feature but deleted before the audit: not judged.
- A test that is still red at the end of the story: still red, and the story-close audit fails. A
  test that has only been skipped (an expected failure, a platform skip): never run, listed and not
  failing, since it vouches for no code. The Stop hook blocks on neither.
- A test file that fails to load for a few calls (a typo): those runs say nothing about which tests
  exist, and its tests are not born again when it loads.
- A call that changes only documentation or `tasks.md` alongside tests: documentation is neither
  test nor source and does not make a change mixed.
- The branch is switched, created from the current state, renamed or rebased mid-feature: births
  are found along the branch's own line of records, and a visit to another branch is not part of
  it.
- Two sessions, or parallel tool calls, writing in the same worktree: their changes interleave in
  one ledger; a test and its code written concurrently, or a second call that finishes before the
  first call's hook takes its snapshot, land in one record under the first call's name and are
  judged born with their code. That fails closed; concurrent writers are outside the supported
  workflow (FR-016).
- Tests that arrive with commits the ledger did not see written — a merge, a fast-forward, a pull,
  a cherry-pick, from this worktree or another: unobserved. The fragment keeps a feature's work on
  its branch, in its worktree, with code-writing subagents one at a time.
- Content brought in without a commit — `git checkout <rev> -- <file>`, a patch applied: one call
  changing tests and code, judged born with its code, which is what the record shows. A `git stash`
  and `git stash pop` brings back tests exactly as they were, which keep their verdicts.
- A test written and committed in the same call: imported, so unobserved. The fragment commits in
  calls of their own.
- HEAD on the default branch, or a local merge into it: the audit refuses on the default branch, and
  the base is the remote-tracking default branch, which a local merge does not move.
- A subagent working in a scratch copy outside the worktree: its calls do not change this
  worktree's state and add nothing to its ledger; code drafted there and pasted in later is not
  distinguishable from code written in place (the audit checks order, not independence).
- Recording a snapshot fails (disk full, repository locked): the agent is told after that call; the
  failure is never silent.
- A test that is flaky at a replayed record: replay can differ from the original run; the audit
  reports the outcome it observes on replay and does not claim the original run.
- Replaying a record hangs: the run is stopped by a deadline that kills its process group, and the
  test is reported as not judged, failing the audit.
- The replay environment imports the project's code from the real worktree instead of the replayed
  one: a test accepted because it passed against other code is checked to fail without any source
  file, and is not accepted when it does not.
- Files ignored by git are part of no record; the installer refuses test patterns that match no
  tracked file.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After every agent tool call in a repository where the ledger is installed, the preset
  MUST record the state of the tracked and untracked-but-not-ignored files of that call's git
  worktree, whichever tool or process wrote them, including calls made by subagents.
- **FR-002**: A call that leaves the worktree as the previous record left it MUST NOT add a record.
- **FR-003**: Each record MUST carry the time, the session, for a subagent its identifier, the tool
  and call, the branch and the HEAD commit, and MUST be kept per worktree and survive the
  repository's garbage collection.
- **FR-004**: Recording MUST NOT block or alter the agent's tool call; a failure to record MUST be
  reported to the agent after that call.
- **FR-005**: When a call changes files matching the project's test patterns and files matching its
  source patterns, the agent MUST be told after that call, with both groups of files named; files
  matching neither MUST count as neither.
- **FR-006**: The audit MUST determine the tests that are new — present at the newest record of the
  current branch, absent at the base commit — from per-test results read from JUnit XML written by
  the project's configured command, run on one test file at a time. The base defaults to the merge
  base with the default branch.
- **FR-007**: For each new test, the audit MUST find, along the current branch's own line of
  records, its birth (the record where it last appeared after being absent, as observed at the
  records that changed its file and, when it appeared without its file changing, at the records
  between; a test that arrived with commits the ledger did not see written has none; a test restored
  with its file exactly as when it was accepted keeps that verdict), the first record from there
  where it ran, and, when that run did not pass, the first record where it passed; each by replaying
  its file at that record in an isolated copy of the worktree. A run that writes no results, or
  reports exactly what the same command reports for that file replaced by unparseable content, MUST
  NOT end a stretch.
- **FR-008**: A run's outcome for a test MUST be failed for a failure or an error, skipped, or
  passed; skipped runs MUST be passed over in finding the first run.
- **FR-009**: The audit MUST report each new test as one of: red (its first run did not pass, and
  the test side as it stood before the call that made it pass passes after that call); predates the
  feature (its first run passed, it fails without any source file, and it passes against the base's
  code); refactored (its first run passed, it fails without any source file, and its call — not one
  that changed test-side paths and any other path together — replaced at least as many accepted
  tests of the feature as it added passing ones; it lists them); born with its code (its first run
  passed, and that call changed source); born green (its first run passed otherwise, or it passes
  without any source file); rewritten to green (its test side from before the call that made it pass
  fails after that call); still red; unobserved; not judged (a replay exceeded its deadline; the
  order could not be told because the earlier test side does not load; its file does not load, or
  its command wrote no JUnit, at the newest record; or the base's run of its file was inconclusive);
  never run (only skipped so far).
- **FR-010**: The audit MUST exit zero only when every new test is red, predates the feature, is
  refactored or never ran, and non-zero otherwise; it MUST list the tests that never ran.
- **FR-011**: Every replay MUST run under a deadline that kills the command's whole process group.
- **FR-012**: The audit MUST NOT read the agent's account of its runs (`tasks.md` or any other file
  the agent writes as evidence).
- **FR-013**: The project's configuration — test file patterns, source file patterns, and the
  command that runs one given test file and writes JUnit XML to a given path — MUST be given at
  install and committed in the repository.
- **FR-014**: Installing the ledger MUST be one commit holding only the ledger's two hook entries
  and the configuration — creating `.claude/settings.json` when it does not exist — and MUST refuse,
  leaving the repository unchanged, on: not being at the repository root with `.specify/`; a
  detached HEAD; no base resolving (data-model.md, Base); anything staged; a settings file that is
  untracked, tracked with uncommitted changes, ignored, not a regular file or marked skip-worktree;
  an existing entry for the ledger; HEAD on the default branch; an incomplete configuration; test
  patterns matching no tracked file; `jq` missing; a commit hook rejecting the commit.
- **FR-015**: The `speckit-implement` fragment MUST install the ledger before the first task when it
  is not installed, and MUST say so in the completion report when it cannot.
- **FR-016**: The `speckit-implement` fragment MUST instruct that each case's test is written and
  run in a call that changes no source file, that source changes come in a later call, that tests
  are renamed or consolidated in calls that change no source file, that commits are made in calls
  of their own, and that subagents writing code work in this worktree, one at a time.
- **FR-017**: The `speckit-implement` fragment MUST NOT require the agent to record red runs, and
  MUST NOT offer breaking the code on purpose as the way to accept a test that passed on its first
  run.
- **FR-018**: The `speckit-implement` fragment MUST run the audit at the close of each user story,
  before the independent review, give its report to the reviewer, and prescribe the remedy of each
  failing verdict as data-model.md lists it: the redo sequence for a test born with its code, born
  green or rewritten to green; the configuration for one that passes without sources; the code, in a
  call that changes no test-side path, for one still red; the redo sequence for one unobserved; and
  the reason's remedy for one not judged.
- **FR-019**: The story review MUST use the project's mutation check where the project's
  constitution or CI names one, and hand-written wrong versions otherwise.
- **FR-020**: The `speckit-tasks` fragment MUST add a property case to the test list of a task that
  implements an invariant the spec states, and only then.
- **FR-021**: The release MUST be 2.0.0, with a CHANGELOG entry and README migration notes; a
  `tasks.md` from 1.x MUST remain readable, and an installed 1.x Stop gate MUST keep running.
- **FR-022**: The README MUST state, as one closed list that every limit stated elsewhere is added
  to: that only Claude Code is verified, and pytest the only runner verified end to end; that
  runners without JUnit XML output, or unable to run one test file on its own (Go), are not
  supported; that the audit checks order, not strength; that it assumes an agent taking shortcuts,
  not one forging the ledger; that a changed body of an already accepted test is not judged; that a
  test added to an unchanged test file by a change elsewhere is not found; that tests arriving with
  commits the ledger did not see written are unobserved; that a restored test keeps its verdict
  whatever code now stands beside it; that replays use the environment at audit time and observe
  flaky tests as they behave on replay; that the audit's cost for compiled languages is not
  measured; that the Stop hook shows a failing verdict once per turn and does not prevent the turn
  from ending; and that the ledger stores every tracked and untracked-but-not-ignored file of the
  worktree, an un-ignored secret included, locally, which `git push --mirror` would send, and no
  git-ignored file; that concurrent writers in one worktree are unsupported and fail closed; and
  that code drafted outside the worktree and brought in later is not distinguishable from code
  written in place; that a test that existed at the base and changed in the feature is not judged;
  and that a test new in the feature but deleted before the audit is not judged.
- **FR-023**: Each rule added to or removed from a fragment MUST carry its evidence in the README
  (constitution III), and every script MUST have a test suite run in CI (constitution IV).
- **FR-024**: At the end of every turn — except on a detached HEAD, on the default branch, or when
  a Stop hook already blocked this turn — the audit MUST run within a time budget and block the
  turn once when a new test has a verdict of born with its code, born green or rewritten to green,
  naming each, or once with its error when the audit cannot run (a malformed configuration, no
  resolvable base, a git error); it MUST NOT block for a test still red, never run, unobserved or
  not judged, nor for a birth the budget left unjudged.
- **FR-025**: Every test whose first run passed MUST first be run with every source path removed
  from the replayed tree; one that still passes MUST be reported as born green, with the reason
  that it passes without any source file — before it can be considered as predating the feature
  or refactored.
- **FR-026**: Each audit MUST snapshot the worktree first when it differs from the newest record,
  and MUST reuse the outcome of any replay already made on the same tree, file and command.
- **FR-027**: The base MUST be the merge base with the remote-tracking default branch when the
  repository has an `origin` remote, resolved without network access, and the audit MUST refuse on
  the default branch itself, so a local merge cannot empty the set of new tests.
- **FR-028**: Replays MUST take the test side and the rest of the tree as wholes — the test side
  from one record, everything else from another — so that a change outside the source and test
  file patterns cannot pass unjudged.

### Key Entities

- **Record**: the state of one worktree after one tool call — when, which session, which subagent,
  which branch — linked to the record before it.
- **Ledger**: the ordered records of one worktree.
- **Effective history**: the records of one branch's line of work, skipping visits to other
  branches.
- **Birth**: the record at which a test, absent before, last appeared (FR-007): observed at the
  records that changed its file, and at the records between when it appeared without its file
  changing; none for an imported test.
- **Verdict**: an audit's judgement of one new test, one of the ten in FR-009, with the record and
  the call it rests on.
- **Configuration**: the project's test patterns, source patterns and JUnit command.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the recorded sequences of quickstart step 4 marked SC-001, reproducing the observed
  failure (code and test in one call),
  100% of those tests are reported as born with their code, and the audit fails.
- **SC-002**: On the recorded sequences of quickstart step 4 marked SC-002: on a sequence that
  follows the cycle (test alone, red, then code), 0 tests fail the audit; on one where code comes
  one call before its test, or the test is rewritten in the call that turns it green, 100% of those
  tests fail it.
- **SC-003**: Recording adds at most 100 ms per tool call — the median of five snapshots of a
  scratch repository of 1,000 tracked files and no untracked ones — with the machine's model and OS
  recorded beside the result.
- **SC-004**: For a pytest project whose single-file run takes about 2 seconds, on the development
  machine: a Stop audit after a turn that added one test and its code completes within 30 seconds;
  a story-close audit of a feature with 60 new tests in 20 test files completes within 2 minutes
  when the Stop hooks have run through the feature (the memo is warm), and within 15 minutes from
  an empty memo (an estimate of 290–430 runs; to be measured). Compiled-language projects are not
  measured.
- **SC-005**: A project moving from 1.6.0 to 2.0.0 keeps its Stop gate running and its old
  `tasks.md` readable, with no manual step beyond the documented update command.
- **SC-006**: In the first feature implemented with 2.0.0, the audit's verdicts are reported per
  story. They are compared with the 27-of-60 first-run passes of 1.6.0 as direction only: 1.6.0
  counted the agent's own records, 2.0.0 counts observed births.

## Assumptions

- The integration is Claude Code, whose post-tool hooks fire for every tool, subagents included,
  and pass the session, the subagent and the working directory, and whose Stop hooks can block a
  turn once (Claude Code hooks reference, read 2026-10-07).
- `git` and `python3` are on the path: Spec Kit's own scripts already need `python3` once a preset
  is installed.
- The project's test runner can run one test file and write JUnit XML for it (pytest, Jest,
  Vitest and PHPUnit can; Go cannot — its unit is the package); pytest's and Vitest's reports were
  measured on 2026-10-07 and Jest's and PHPUnit's were not, and the one verified end to end with
  this feature is pytest.
- A test is identified by its file and its name as the JUnit XML reports them.
- Replaying a record uses the project's installed environment at audit time, not the one it had
  when the record was made; the configured command is responsible for pointing at it.
- The agent may take shortcuts but does not forge the ledger or remove its hooks (research.md R0).
