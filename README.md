# spec-kit-preset-test-first

A [Spec Kit](https://github.com/github/spec-kit) preset that makes test-first
the default instead of an opt-in, and observed instead of reported. It appends
to two core skills and replaces nothing, so upstream changes to the rest of
each skill keep arriving. It ships the scripts those skills run: a ledger that
records the worktree after every Claude Code tool call, an audit that replays
the records to show each new test failed before its code, and the installer
of a Stop hook that gates every turn on the test suite.

| Skill | What the preset adds |
|---|---|
| `speckit-tasks` | Tests are required (overriding core's "Tests are OPTIONAL") for behaviour with logic of its own; one task per behaviour, carrying its test list — concrete cases, input and expected result, taken from the spec before any code exists, simplest first; no separate test tasks and no predicted failures; never `[P]`; tasks cite their `FR-`/`SC-` IDs; every test runs under a time limit, set by a setup task where the framework has none; a task implementing an invariant the spec states gets a property case over generated inputs |
| `speckit-implement` | The ledger (below) is installed before the first task; the suite's per-test time limit is confirmed; one red-green-refactor cycle per case of the task's list, the test written and run in a call that changes no source, failing from inside, the code in a later call; renames, consolidations and commits in calls of their own, and writing subagents in this worktree, one at a time; a test that passes on its first run is not justified by breaking the code — if its code came first, it is redone; a case's expected result is never changed to reach green — one believed wrong is stopped and reported as a spec gap; a case found mid-implementation joins the list; a task is marked done only on a green suite and no lint or type finding beyond a baseline; ignore files and tool config are touched only as far as the feature needs; each completed user story is audited, then reviewed from a fresh context that gets the audit's report, runs the project's mutation check or tries wrong versions by hand, each run under a deadline that kills its process group, and reads the code for what the refactor step should have removed; the first green suite installs the Stop gate (below) |

## Observed test-first

Up to 1.x the agent recorded its own red runs in tasks.md. In the run that
motivated 2.0.0 (research L1), 27 of about 60 cases were recorded as passing
on their first run, and 11 test runs each came from one shell command that
wrote a test and the code it covers together, then ran it green; the record said
"passed on first run". A report written by the author is the defect. So 2.0.0
observes instead:

- **The ledger.** A Claude Code `PostToolUse` hook records the worktree after
  every tool call — every tracked and untracked-but-not-ignored file, as on
  disk — as a git tree in a chain of commits under the per-worktree ref
  `refs/worktree/test-first/ledger`, a symbolic ref to the worktree's ledger
  under `refs/test-first/ledgers/`, which a `git gc` run from any worktree
  keeps; a removed worktree's ledger is deleted when the next one is created.
  It works on a copy of the index, so the
  real index and the worktree are never touched. When one call changed test
  and source files together it says so to Claude (exit 2, which shows stderr
  and blocks nothing): a test written with the code that satisfies it will
  fail the audit.
- **The audit.** For each test new since the base (the merge base with the
  remote's default branch), it finds the record where the test was born and
  runs the test's file there, in a scratch worktree under a deadline; then at
  each record until it first passes. It reads outcomes from JUnit XML, so it
  works with any runner that runs one file and writes JUnit.
- **The verdicts.** `red`: it failed when written, and the tests written
  before the call that made it pass still pass against that call's code.
  `predates`: it passes against the base's code — the behaviour was there.
  `refactored`: it replaced accepted tests in a call that did not change
  test-side paths together with anything else.
  These pass, as does `never-run` (only ever skipped), which is listed. These
  fail, each printed with its remedy: `born-with-code` (written in the call
  that wrote its code), `born-green` (passing from its first run),
  `rewritten-to-green` (changed in the call that turned it green),
  `still-red`, `unobserved` (no birth in this ledger), `not-judged` (with the
  reason, such as a run that wrote no JUnit; a test file that no run could
  read is reported under its path). The remedy for the first three is
  the redo sequence: remove the test (its file, when it is the file's only
  test), revert its code, write the test again alone, see it fail, restore
  the code — with a stub of the code first, in
  a call of its own, for a test whose file did not load before its code. A
  test born green because it passes without any source file is fixed in the
  configuration instead, committed on its own: `run` reaches code outside the
  replay, or `sources` misses the code the test exercises.
- **The Stop hook.** The same audit runs at the end of every turn within a
  120-second budget, reusing every run already made, and blocks the turn once
  when a new test was born with its code, born green or rewritten to green,
  or when the audit cannot run (a configuration or git error, the preset's
  `run-bounded.sh` missing, an OS error such as a full disk). It stays
  silent where there is nothing to judge — no configuration, no ledger, a
  detached HEAD, the default branch — and on a stop that continues a turn it
  already blocked. It takes the files changed most recently first and replays
  what the turn changed, plus one run for each file whose tests are still red
  or not yet run; the rest comes from earlier turns' runs. A birth
  the budget leaves unjudged waits for the next turn or the story's audit.
  `/speckit-implement` runs the audit in full at each story's close, before
  the review.

The audit checks order, not strength: that a test failed before its code, not
that it tells right behaviour from wrong. Strength is the story review's,
through the project's mutation check where it has one.

### Configuration

`.specify/test-first.json`, written and committed by the installer, which
`/speckit-implement` runs before its first task:

```bash
python3 .specify/presets/test-first/scripts/python/cli.py install \
  --tests 'tests/**' --sources 'src/**' \
  --run 'PYTHONPATH=src UV_PROJECT_ENVIRONMENT={root}/.venv uv run --no-sync python -m pytest -q -p no:cacheprovider --junitxml={junit} {file}'
```

`--tests` is the whole test side — tests, helpers, fixtures; `--sources` the
code; both are git globs. `--run` runs one test file, `{file}`, and writes
JUnit XML to `{junit}`, inside a scratch worktree that holds only the
record's files: `{root}`, the real worktree, is how it reaches the installed
environment, and `PYTHONPATH=src` keeps a packaged project's editable install
from importing the real worktree's code instead of the record's. For a Node project:
`ln -s {root}/node_modules node_modules && node_modules/.bin/vitest run {file} --reporter=junit --outputFile={junit}`.
The installer commits the configuration and the two hook entries in
`.claude/settings.json` as one commit, or refuses and leaves the repository
as it was: outside the repository's root or without `.specify/` there, off
the feature's branch, without a base it can resolve, with something staged,
with a `settings.json` or configuration file it could not commit whole (untracked,
changed, ignored, skip-worktree, a symlink or inside a symlinked directory,
not a settings object), with a ledger entry already there, with globs git
cannot use or that match no tracked test, without the preset's
`run-bounded.sh`, when a commit hook rejects it or outlives the commit's
300-second deadline, or when it is terminated during its commit. A commit
that landed stands when what follows it fails or is stopped (a `post-commit`
hook), and the installer says so.
The audit by hand: `python3 .specify/presets/test-first/scripts/python/cli.py audit`.

### Limits

What the audit does not check, and where it does not hold:

- Only Claude Code is verified. pytest is the runner verified across every
  scenario; Vitest in one.
- A runner without JUnit XML output, or unable to run one test file on its
  own (Go, whose unit is the package), is not supported.
- It checks order, not strength.
- It assumes an agent taking shortcuts, not one forging evidence: the agent
  can write the ledger's ref and the hook settings.
- The body of an already accepted test changed to cover new code is not
  judged: a test's identity is its name.
- A test added to an unchanged test file by a change elsewhere (generated
  cases) is not found as new.
- Tests arriving with commits the ledger did not see written (a merge, a
  cherry-pick), or written and committed in one call, are `unobserved`.
- Test and code brought in together by one call that copies rather than
  writes (`git checkout <rev> -- <path>`, a patch) are `born-with-code`.
- A `--run` that imports the real worktree's code instead of the record's —
  an editable install, a workspace package linked into `node_modules` — makes
  a test written first look `born-green`; the uv recipe above prevents it for
  a src layout, and a pnpm workspace is not tested.
- The ledger is local to each worktree and stays on its machine: neither the
  preset nor a plain `git push` sends it (`git push --mirror` would, below).
  A feature continued in another clone or on another machine starts a new
  ledger there, whose first tool call's record is its origin: the tests
  written before, and those that call writes, are `unobserved`. Finish a
  feature where it started.
- A restored test keeps its earlier verdict, whatever code now stands
  beside it.
- Replays use the environment as it is at audit time, and observe a flaky
  test as it behaves on replay.
- The audit's cost for compiled languages is not measured: every replay
  starts from a clean tree.
- Once any Stop hook has blocked a turn — this one or another, such as the
  Stop gate — the rest of that turn's stops skip the audit: a test born
  after that block is shown at the next turn or the story's audit.
- A hook killed mid-run leaves the call's changes to be recorded under the
  next call's name.
- The Stop hook shows a failing verdict once per turn; it does not prevent
  the turn from ending, judges nothing on the default branch or a detached
  HEAD, and leaves to a later turn the births its 120-second budget does not
  reach. A test that appears in a file the turn did not change (an id
  generated from code) is judged at the story's audit, not at a Stop.
- The ledger stores every tracked and untracked-but-not-ignored file of the
  worktree, an un-ignored secret included, as git objects in the local
  repository; `git push --mirror`, from any worktree, would send every
  worktree's ledger. No git-ignored file.
- Concurrent writers in one worktree are not supported, and fail closed:
  their changes land in one record, so a test and its code written at once
  are `born-with-code`.
- An installer stopped in the instant git writes its commit can leave a ref
  lock (`.git/HEAD.lock`, `.git/refs/heads/<branch>.lock`): git opens a lock
  file before it registers it for removal on a signal. Its commit is built in
  an index of its own, so no lock of the repository is held before the
  commit's hooks, where a stop usually lands; the ref locks come after them,
  for microseconds. git's message names the file to remove.
- Code drafted outside the worktree and brought in later cannot be told from
  code written in place.
- A test that existed at the base and changed in the feature is not judged,
  nor one new in the feature but deleted before the audit.
- On a clone whose index git has not rewritten since checkout, each record
  costs about 230 ms instead of under 100, until any `git status` or commit
  (the installer's included) rewrites it (research L7).
- The hooks need `python3` 3.11 or newer on `PATH`; an older one gets a
  message, not a record.

## Stop gate

The fragments are instructions, and they end with the run. The gate does not:
the first time `/speckit-implement` sees the whole suite green with no gate in
place, it runs

```bash
bash .specify/presets/test-first/scripts/bash/install-stop-gate.sh <test command>
```

which commits `.claude/hooks/stop-gate.sh` and its entry in
`.claude/settings.json`, and nothing else, as one commit of its own. From then
on every Claude Code turn in that repository, on any clone and outside Spec Kit
too, ends by running the suite. A red suite blocks the first stop of the turn
with the failure (exit 2, output on stderr) and lets the second through, so a
test that cannot pass honestly gets reported instead of edited until it does.
The hook runs the suite through the preset's `run-bounded.sh` with a deadline
(`DEADLINE=540` in the hook, under the 600 seconds Claude Code gives it): a
suite that does not finish is stopped with its whole process group and blocks
the turn saying so.
The design and what was tried and dropped are in the script's header.

The installer refuses rather than guesses: a red suite, anything staged, an
uncommitted, symlinked, ignored or skip-worktree `settings.json`, a hook or a
Stop entry for it already there, a missing `run-bounded.sh`, a suite that
does not finish in 540 seconds, or a commit hook that rejects its commit or
does not finish in 300. Stopped, it passes the signal on and waits for git
before putting anything back; a commit that already landed (a `post-commit`
hook) stands, and it says so. To
change the command later, edit `TEST_COMMAND` in the hook. To turn the gate
off, remove its entry under `hooks.Stop` in `.claude/settings.json` and keep
the hook file: the file is what `/speckit-implement` looks for, so the gate
stays off. Removing the file as well, as reverting the feature that installed
it does, means the next run installs it again. Only with `.specify/` at the
repository root, and not where the project has a gate of its own: a Stop
hook whose command or script runs the suite, or a fast subset, and exits 2
when it is red. A hook that runs tests only to notify or log does not count.
The gate's installer needs `jq`; the gate does not. The gate and the
ledger's Stop hook answer different questions — is the suite green, did each
new test fail before its code — and Claude Code runs both at every stop.

## When to use it

- Work where a test that never failed is not evidence: domain logic, money,
  parsing, anything with edge cases.
- Projects that want every task traceable to a requirement ID.

## When not to use it

- Spikes and prototypes, where the point is to learn what to build.
- Features with no logic of their own (copy, styling, configuration): the
  preset exempts such tasks, so it adds little there.

Verified with the Claude Code integration only. The fragments are plain
Markdown and should compose for any integration that registers command
overrides, but that is not tested.

## Install

```bash
specify preset add --from https://github.com/camilopiedra92/spec-kit-preset-test-first/archive/refs/tags/v2.0.0.zip
```

To move a project to a newer release:
`specify preset update test-first --from <that tag's zip URL>`.

From 1.x: update as above and commit `.specify/presets/test-first/`; check
that `python3` on `PATH` is 3.11 or newer. The next `/speckit-implement` on a
feature branch installs the ledger in a commit of its own. The 1.x Stop gate
keeps running, and a tasks.md written under 1.x keeps its recorded red runs;
new cases get none. `tests/compose.sh` checks this from the v1.6.0 archive.

Once any preset is installed, Spec Kit's bash scripts resolve templates with
`python3` and PyYAML. If the `python3` on your PATH lacks PyYAML, point
`SPECKIT_PYTHON_EXECUTABLE` at one that has it — the specify CLI's own uv tool
environment does: `$(uv tool dir)/specify-cli/bin/python`.

## Verified

`tests/compose.sh` installs the preset from a tag-shaped archive into a scratch
project with the real CLI and checks that each skill keeps its core body and
description and ends with the fragment, and that core still carries the rule
the fragments override or narrow, and that the gate installer and the story
review's runner land where the implement fragment runs them.
`tests/stop-gate.sh` runs the installer against a fake suite: what it refuses,
that a refused or failed run leaves the repository as it was, what its commit
holds, and how the hook it writes answers a green, a red, a hung suite, a
missing runner and a second stop.
`tests/run-bounded.sh` runs the runner against commands built to escape it — a
hang, a leader that exits 0 on SIGTERM, a child that ignores SIGTERM, a child
left behind, a pipeline, the runner itself killed — and checks the exit code
and that nothing survives.
For the ledger: `tests/python/` holds the units (pytest, run on Python 3.11
too, with ruff and mypy in strict mode); `tests/ledger.sh` runs the hook as
Claude Code does and times it; `tests/audit.sh` builds ledgers call by call
in scratch projects and runs the audit over 37 scenarios, all but one with real
pytest — test first, code first in one call or one call apart, tests renamed,
consolidated or edited until they pass, commits in their own call, rebases,
a hang, a killed audit — and the other with Vitest; `tests/install-ledger.sh`
installs through the entry point and runs both committed hook commands;
`tests/compose.sh` also updates a project from the v1.6.0 archive and checks
its Stop gate and its 1.x tasks.md still work. CI runs all of them, against
the pinned Spec Kit release on every push and against the latest release
weekly.

Measured on 2026-10-07, macOS on an M-series Mac (Mac16,8), git 2.55.0
(research L7): a record costs a median of 82–96 ms per call on 1,001 tracked
files, depending on the machine's load, and 91–94 ms on a clone of renta (861
files) once git has rewritten its index, the hook on Python 3.14.7; an audit of 60 new tests in 20 files,
pytest 9.1.1 on Python 3.12.12, took 26–29 s from an empty memo and 8–9 s
warm. A Stop turn with one test and its code took 1–2 s in a one-file
project and, on 2026-10-08, 6 s after that 20-file feature, all its tests
green (10 s before a Stop stopped replaying files the turn left unchanged;
one run each, directional). On a ledger of
15,000 records the Stop audit of one test took under a second; before its
history walk became one git process, the Stop audit took 28–29 s at 1,500
records and the story-close audit 4 min 49 s at 15,000 (research L7, one run
per size).

With v1.0.0, in one pilot (Spec Kit 1.1.0, 2026-10-05), `/speckit-tasks`
produced 61 tasks, 52 citing requirement IDs, against 29 and 5 without the
preset; that version still wrote a test task before each implementation task.

v1.5.0, the same feature implemented on Spec Kit 1.1.0, 2026-10-05, from the
same spec, plan and contract (one run per arm, so directional):

| Story 1 | v1.4.1: a test task before each implementation task | v1.5.0: one task per behaviour with its test list |
|---|---|---|
| Tasks | 26 | 9 |
| Test methods at the end of the story | 27 | 62 |
| Test gaps the story review found | 6 | 3, plus 1 the implementer found itself |
| Red run recorded for each case | yes | yes, with a deliberate break for each case that passed first |
| `/speckit-analyze` rounds before implementing | 3; about a fifth of their findings (7–8 of 36) corrected predicted failures | not run: B started from the artifacts A's rounds had already fixed |

Arm A packs several cases into `subTest` loops, so its 27 methods understate
its cases; in B 28 evidence entries, covering about 40 cases, record a
first-run pass confirmed by breaking the code on purpose. The Stop gate installed itself in both arms: in A
at the first green run, in B only after its first task closed, which the
wording then allowed and v1.5.0 now rules out. In a copy
with one deliberately broken format string (16 tests red), a turn asked only to
reply "done" was blocked by the gate and ended with the code fixed.

Validated in a clone of renta (861 files) on 2026-10-07, with Claude Code
2.1.293 in `claude -p` sessions, Spec Kit 1.1.0, git 2.55.0, pytest 9.1.1 on
Python 3.14.7, macOS: the preset updated from 1.6.0, the ledger installed on a
feature branch, then a session told to write a test against a stub in a call
of its own, run it red, write the code, and then write a second test and its
code in one shell command. The hook told Claude at that call; the Stop audit
blocked the turn; the audit gave `red` and `born-with-code`. A fourth session
ran the installer itself, as `/speckit-implement` does, then a stub, the test
and the code: Claude Code picked up the committed hooks within the session,
recorded every later call, and the audit passed with `red`. The two sessions
before it found two defects, fixed in this release: the ledger had no record
before the first tool call, so the first test written was `unobserved`; and a
test whose file could not import its code yet was `born-with-code` without
saying why, which the session read as a false positive. One run each,
about $0.44 per session.

Why 2.0.0's rules, by source (searched and measured 2026-10-07; research.md
of feature 001 holds each decision with what was considered and why it
lost):

- Observed, not reported: the renta run on 1.6.0 (research L1, one feature,
  directional) — 27 of about 60 cases recorded as first-run passes, 11 test
  runs each from one command that wrote test and code together. Every spec-driven
  framework surveyed asks for test-first and none observes it; those that
  "check" it check the agent's own report (L3). Böckeler: "a red test tells
  you the agent ran it and saw failure, not that the failure was for the
  right reason" ([martinfowler.com](https://martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html)).
- The worktree after every call, not the agent's commands: the writes in L1
  came through shell heredocs, which a hook watching file edits does not see,
  and parsing shell for writes is unsound (spec-gates v0.4.0 spends 1,347
  lines on it and still allows `python3 - <<EOF`; research R1). Claude Code's
  checkpoints do not see Bash writes ([best practices](https://code.claude.com/docs/en/best-practices)).
- Fail-to-pass at each test's birth, and a green check at the call that turns
  it green: SWE-bench's criterion for a test that encodes a change
  ([arXiv 2310.06770](https://arxiv.org/abs/2310.06770)), applied when the
  test was written; the green check catches the test edited until it passes
  that ImpossibleBench documents (research R5).
- A runner's JUnit XML, one file per run, load failures measured at each run:
  pytest 9.1.1 and Vitest 5.0.3 report a file that cannot load in different
  shapes, so the audit compares against the same command on the same tree
  with the file made unparseable rather than encode either (research R6, L7).
- A Stop hook that blocks once per turn: the deterministic gate the best
  practices name, with the way out ImpossibleBench found cut cheating from
  54% to 9% for GPT-5 (research R12).
- The review's mutation check where the project has one: Böckeler moved to
  mutation testing for regression quality; reporting mutants on the code
  under review is Google's practice (research R8).
- Property cases for stated invariants: Kiro derives correctness properties
  from requirements ([kiro.dev](https://kiro.dev/docs/specs/correctness)), and
  agentic property-based testing found valid bugs in 56% of its reports
  across 100 packages ([arXiv 2510.09907](https://arxiv.org/abs/2510.09907)) —
  evidence that properties find bugs, not a measurement inside a test-first
  list, so directional (research R9).
- The story audit's verdict counts in the completion report, per story:
  SC-006 compares the first feature on 2.0.0 with the 27 of about 60
  first-run passes of 1.6.0, as direction only (1.6.0 counted the agent's own
  records), and per story is the unit the audit runs at.
- A stub raises rather than returning a placeholder, and a task's property
  case is written with its first case, before any code: reasoning from the
  audit's own rule, not measured on its own. A property case written after its
  code passes at its first run, which is `born-green` by definition (FR-009);
  and a placeholder can satisfy a property (a total that returns 0 is never
  negative), so the case would pass against the stub. Sentinel stubs made
  every test fail trivially in the 2026-10-05 pair of runs below; the
  sessions that validated 2.0.0 used a raising stub (research L7).
- Writing subagents one at a time, in the feature's worktree (narrowing
  core's "parallel tasks [P] can run together"): a subagent in a worktree of
  its own records into a ledger the feature's audit never reads, and two
  writers at once land in one record, judged `born-with-code` (research R1,
  R14). Reasoning from the ledger's design, not measured.
- Renames and consolidations in calls that change only test-side paths, and
  commits in calls of their own: reasoning from the audit's own rules, not
  measured on their own. A call that replaces accepted tests is `refactored`
  only when it changes the test side alone, and only up to as many passing
  tests as it replaced (research R13); a test written and committed in one
  call arrives in HEAD as if from elsewhere, so it is `unobserved` (R14).
- The redo removes a test's file when it holds the only test: Vitest 5.0.3
  reports a file without tests the way it reports a file that cannot load,
  so an emptied file would read as inconclusive rather than as the test gone
  (research R6, from the JUnit probes in L7).
- The review copy's `PostToolUse` entries are removed with its `Stop` ones: a
  session in the copy would otherwise record the reviewer's wrong versions
  into the copy's ledger and be blocked by its Stop audit, as by the 1.x gate.
  Reasoning, not measured.
- Removed, recording red runs and breaking the code on purpose to accept a
  first-run pass: the first is what the ledger observes; the second could not
  tell behaviour that existed before the task from code written a moment
  earlier (L1), and the redo sequence is the same act, observed (research
  R10).
- Not adopted: a separate test-writing agent (no gain at 3–8.5 times the
  tokens, Böckeler, two runs per arm); an LLM judging every write (TDD Guard,
  Probity: still a model's verdict, blind to shell writes unless shells are
  denied); code-writing subagents in worktrees of their own (each records
  into a ledger of its own, which the feature's audit never reads); an index kept between hook calls (measured 8 times
  faster on a fresh clone, reverted after review: it kept recording files the
  real index had stopped tracking; research R2).

Why 1.x's rules, by source (searched 2026-10-05):

- One case at a time from a test list that grows as cases are found: Kent
  Beck, [Canon TDD](https://newsletter.kentbeck.com/p/canon-tdd), which names
  turning the whole list into tests up front as a mistake ("Rework.").
- Cases taken from the spec before any code exists: tests generated without
  seeing the code caught about 25% of faults against about 14% when generated
  after erroneous code ([arXiv 2607.05139](https://arxiv.org/html/2607.05139)).
- Expected results not changed to reach green, with a way to stop and report:
  on impossible SWE-bench tasks GPT-5 cheated in 54% and o3 in 49%; a way out
  cut GPT-5 to 9%, though the paper finds the effect much smaller for Claude
  Opus 4.1 ([ImpossibleBench](https://arxiv.org/abs/2510.20270)), so the rule
  pairs it with the story review's check of tests against the list.
- A deterministic gate and a verifier that is not the author: Claude Code's
  [best practices](https://code.claude.com/docs/en/best-practices) ("hooks are
  deterministic"; a verification subagent "so the agent doing the work isn't
  the one grading it").
- Not adopted, for lack of evidence: a separate test-writing agent, and more
  ceremony around cycle size. The only direct comparison of strict TDD with
  agents found no gain at 3 to 8.5 times the tokens
  ([Böckeler](https://martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html)).
- Not adopted after measuring it: one cycle per task instead of per case
  (the task's whole list written as tests, watched failing, then the code).
  A fresh pair of runs on Story 1 of the same feature, Spec Kit 1.1.0,
  2026-10-05, both from one shared tasks.md and differing only in the
  implement fragment, one run each. Per-task cost 20% less ($4.26 against
  $5.33, 50 turns against 78), and the end state was the same: 45 of 45 on a
  held-out black-box suite written from the spec, and 25 of 27 wrong versions
  caught from a fixed catalog applied blind. But the cycle's own checks went
  quiet. Its stubs returned sentinels, so every test failed trivially and a
  deliberate break was needed once, against 40 first-run passes broken on
  purpose per case. It found no cases during implementation, against four.
  The story review then closed 9 test gaps, against 5. The same end quality
  rested on one layer instead of two, and 20% of the cost does not pay for
  losing one.

