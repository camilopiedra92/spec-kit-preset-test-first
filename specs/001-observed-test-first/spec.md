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
transcript, 11 test runs came from a single tool call — most often a shell command, not the
file-editing tool — that wrote the production code and its test together and ran green; the case
was then justified by breaking the code on purpose, as the 1.6.0 fragment allows ("A new test that
passes on its first run has not been watched failing. Break the code it pins on purpose..."). The
red runs recorded in `tasks.md` are written by the same agent that writes the code.

No spec-driven framework surveyed on 2026-10-07 verifies the order: Spec Kit core, Kiro, BMAD,
obra/superpowers and OpenSpec prompt for test-first; TDD Guard and its successor Probity judge each
write with a language model and are bypassed by shell writes. What fault detection is measured to
depend on is that the test is written without the code in view (arXiv 2607.05139: 25% of faults
found against 14% when written after faulty code). The industry's mechanical check that a test
encodes new behaviour is SWE-bench's FAIL_TO_PASS: the test fails before the change and passes
after. This feature applies that check at the moment each test was written.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A test written together with its code is caught (Priority: P1)

A project owner runs `/speckit-implement` with the preset. The agent writes code however it likes —
the file-editing tool, a shell heredoc, a script, a subagent. At the close of each user story, an
audit reads what the repository looked like after every tool call and, for every test that is new
in the feature, replays that test as it was when it first appeared. A test that first appeared in
the same tool call as a source change is reported as born with its code, and the audit fails. A
test that first appeared alone and failed there is proven red. The owner and the story's reviewer
read the audit, not the agent's account of its own red runs.

**Why this priority**: it is the defect observed. Without it every other part of the preset still
rests on the agent's self-report.

**Independent Test**: in a scratch repository with the ledger installed, replay two recorded
sequences of tool calls — test then code; test and code in one shell call — and run the audit: the
first is proven red, the second is born with its code and the audit exits non-zero.

**Acceptance Scenarios**:

1. **Given** a feature in which a test was added by one call and its code by a later one, **When**
   the audit runs, **Then** the test is reported as failed at birth and the audit passes.
2. **Given** a feature in which one shell call added a test and a source change, **When** the audit
   runs, **Then** the test is reported as born with its code, the call is named, and the audit
   fails.
3. **Given** a test added alone that passes at once because an earlier cycle's code already covers
   it, **When** the audit runs, **Then** it is reported as passed at birth for the reviewer to
   judge, and on its own it does not fail the audit.
4. **Given** a test whose first run errors because the code it imports does not exist yet, and a
   later call adds a stub under which it fails, **When** the audit runs, **Then** it is classified
   by that first non-error outcome: failed, so proven red.
5. **Given** a test born with its code that the agent then redid — removed the test, reverted the
   code, wrote the test again, saw it fail, restored the code — **When** the audit runs, **Then**
   the test's latest birth is the one judged, and it is proven red.

---

### User Story 2 - The agent hears it at once (Priority: P2)

When a single tool call changes test files and source files together, the agent is told
immediately after that call, with the files named, so it can redo the cycle while it is cheap
instead of finding out at the story's close.

**Why this priority**: the audit is the guarantee; this is what keeps the audit's failures rare.

**Independent Test**: install the ledger in a scratch repository, simulate a tool call that changes
a test file and a source file, and read the message returned to the agent; simulate one that
changes only a test file and see no message.

**Acceptance Scenarios**:

1. **Given** the ledger installed, **When** a call changes a test file and a source file, **Then**
   the agent receives a message naming both groups of files.
2. **Given** the ledger installed, **When** a call changes only test files, only source files, or
   neither, **Then** the agent receives no message from the ledger.
3. **Given** a call that renames a symbol across code and tests (a refactor), **When** it completes,
   **Then** the message appears, but the audit does not fail on it, because no test was born in it.

---

### User Story 3 - The implement workflow runs on observed evidence (Priority: P2)

The project owner's `/speckit-implement` installs the ledger before the first task; takes each case
as a test written and run in a call that touches no source file, then the code in a later call;
closes each story with the audit and then the independent review; and no longer asks the agent to
record its own red runs or to justify a first-run pass by breaking the code. Where the project has
a mutation check — named by its constitution or run by its CI — the story review uses it to measure
the tests' strength; otherwise the reviewer writes wrong versions by hand, as today.

**Why this priority**: it is how the ledger and the audit reach a project.

**Independent Test**: compose the preset into a scratch Spec Kit project and read the composed
`speckit-implement` skill for each instruction above; install from the composed instructions in a
scratch repository and see the ledger recording.

**Acceptance Scenarios**:

1. **Given** a project without the ledger, **When** `/speckit-implement` starts, **Then** the ledger
   is installed and committed before the first task, with the project's configuration.
2. **Given** a completed user story, **When** the story closes, **Then** the audit runs before the
   independent review and the review receives its report.
3. **Given** an audit that reports a test born with its code, **When** the agent remedies it,
   **Then** it follows the redo sequence of Story 1, scenario 5, and reruns the audit.
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
- A test moved or renamed: it is new under its new name and is born in the call that moved it; if
  that call changed no source, it is reported as passed at birth for the reviewer.
- A test that existed at the base and is changed in the feature: it is not new and is not judged
  by birth; only tests absent at the base are.
- A test new in the feature but deleted before the audit: not judged.
- A test that only errors until the end: reported as never run, and the audit fails.
- A call that changes only documentation or `tasks.md` alongside tests: documentation is neither
  test nor source and does not make a birth mixed.
- Two sessions working in the same worktree: their calls interleave in one ledger; each record
  names its session, and the audit judges births regardless of session.
- A subagent working in a scratch copy outside the worktree: its calls do not change this
  worktree's state and add nothing to its ledger.
- Recording a snapshot fails (disk full, repository locked): the agent is told after that call; the
  failure is never silent.
- A test that is flaky at birth: replay can pass where the original run failed; the audit reports
  the outcome it observes on replay and does not claim the original run.
- Replaying a record hangs: the run is stopped by a deadline that kills its process group, and the
  test is reported as not judged, failing the audit.
- Files ignored by git are part of no record; the installer refuses test patterns that match no
  tracked file.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After every agent tool call in a repository where the ledger is installed, the preset
  MUST record the state of the tracked and untracked-but-not-ignored files of that call's git
  worktree, whichever tool or process wrote them, including calls made by subagents.
- **FR-002**: A call that leaves the worktree as the previous record left it MUST NOT add a record.
- **FR-003**: Each record MUST carry the time, the session and, for a subagent, its identifier, and
  MUST be kept per worktree and survive the repository's garbage collection.
- **FR-004**: Recording MUST NOT block or alter the agent's tool call; a failure to record MUST be
  reported to the agent after that call.
- **FR-005**: When a call changes files matching the project's test patterns and files matching its
  source patterns, the agent MUST be told after that call, with both groups of files named; files
  matching neither MUST count as neither.
- **FR-006**: The audit MUST determine the tests that are new in a range — present at its end,
  absent at its base commit — from per-test results read from JUnit XML written by the project's
  configured command. The base defaults to the merge base with the default branch.
- **FR-007**: For each new test, the audit MUST find its birth — the first record of the last
  continuous stretch of records in which it exists — and its outcome there, by replaying its file
  at that record in an isolated copy of the worktree.
- **FR-008**: A test whose birth is an error MUST be classified by its first non-error outcome in
  later records; one that never reaches a non-error outcome MUST be reported as never run.
- **FR-009**: The audit MUST report each new test as one of: failed at birth; born with its code
  (its birth record's call also changed source files); passed at birth (a test-only call);
  unobserved; never run; not judged (replay exceeded its deadline).
- **FR-010**: The audit MUST exit non-zero when any new test is born with its code, unobserved,
  never run or not judged, and zero otherwise; passed-at-birth tests MUST be listed and MUST NOT on
  their own fail it.
- **FR-011**: Every replay MUST run under a deadline that kills the command's whole process group.
- **FR-012**: The audit MUST NOT read the agent's account of its runs (`tasks.md` or any other file
  the agent writes as evidence).
- **FR-013**: The project's configuration — test file patterns, source file patterns, and the
  command that runs given test files and writes JUnit XML to a given path — MUST be given once at
  install and committed in the repository.
- **FR-014**: Installing the ledger MUST be one commit holding only the ledger's hook entry and the
  configuration, and MUST refuse, leaving the repository unchanged, on: anything staged; a settings
  file that is uncommitted, ignored or not a regular file; an existing entry for the ledger; an
  incomplete configuration; test patterns matching no tracked file.
- **FR-015**: The `speckit-implement` fragment MUST install the ledger before the first task when it
  is not installed, and MUST say so in the completion report when it cannot.
- **FR-016**: The `speckit-implement` fragment MUST instruct that each case's test is written and
  run in a call that changes no source file, and that source changes come in a later call.
- **FR-017**: The `speckit-implement` fragment MUST NOT require the agent to record red runs, and
  MUST NOT offer breaking the code on purpose as the way to accept a test that passed on its first
  run.
- **FR-018**: The `speckit-implement` fragment MUST run the audit at the close of each user story,
  before the independent review, give its report to the reviewer, and prescribe the redo sequence
  for each test born with its code.
- **FR-019**: The story review MUST use the project's mutation check where the project's
  constitution or CI names one, and hand-written wrong versions otherwise.
- **FR-020**: The `speckit-tasks` fragment MUST add a property case to the test list of a task that
  implements an invariant the spec states, and only then.
- **FR-021**: The release MUST be 2.0.0, with a CHANGELOG entry and README migration notes; a
  `tasks.md` from 1.x MUST remain readable, and an installed 1.x Stop gate MUST keep running.
- **FR-022**: The README MUST state that only Claude Code is verified, and that frameworks without
  JUnit XML output are not supported.
- **FR-023**: Each rule added to or removed from a fragment MUST carry its evidence in the README
  (constitution III), and every script MUST have a test suite run in CI (constitution IV).

### Key Entities

- **Record**: the state of one worktree after one tool call — when, which session, which subagent —
  linked to the record before it.
- **Ledger**: the ordered records of one worktree.
- **Birth**: the record at which a test, absent in the record before, appears for the last time.
- **Verdict**: an audit's judgement of one new test, one of the six in FR-009, with the record and
  the call it rests on.
- **Configuration**: the project's test patterns, source patterns and JUnit command.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On recorded sequences reproducing the observed failure (code and test in one call),
  100% of those tests are reported as born with their code, and the audit fails.
- **SC-002**: On a sequence that follows the cycle (test alone, red, then code), 0 tests are
  reported as born with their code.
- **SC-003**: Recording adds at most 100 ms per tool call on a repository of about 1,000 tracked
  files, measured on the development machine.
- **SC-004**: An audit of a feature with 60 new tests in 20 test files completes within 10 minutes
  on the development machine, when one run of a test file takes about 2 seconds.
- **SC-005**: A project moving from 1.6.0 to 2.0.0 keeps its Stop gate running and its old
  `tasks.md` readable, with no manual step beyond the documented update command.
- **SC-006**: In the first feature implemented with 2.0.0, the share of tests passing at birth is
  reported per story, so the next release can be weighed against the 27-of-60 baseline.

## Assumptions

- The integration is Claude Code, whose post-tool hooks fire for every tool, subagents included,
  and pass the session, the subagent and the working directory (Claude Code hooks reference, read
  2026-10-07).
- `git` and `python3` are on the path: Spec Kit's own scripts already need `python3` once a preset
  is installed.
- The project's test runner can write JUnit XML for a given set of test files (pytest, Jest,
  Vitest, Go and PHPUnit can); the one verified end to end with this feature is pytest.
- A test is identified by its file and its name as the JUnit XML reports them.
- Replaying a record uses the project's installed environment, not a fresh one; the configured
  command is responsible for pointing at it.
