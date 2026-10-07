# Research: Observed test-first

Decisions for [plan.md](plan.md), each with what was considered and why it lost. Sources were read
or measured on 2026-10-07 unless dated otherwise. The decisions were revised twice the same day,
each time after an independent review in a fresh context, and reviewed a third time: the first
revision added R0, R12 and R13 and the landscape in L3 and L9; the second made replays swap whole
sides of the tree (R5), measured load failures per run (R6) and added R14; the third replaced the
edge rules that kept opening holes — a driving-change check for renames, following merges, a
bisection for births — with a count, `unobserved` and a forward scan (R13, R14, data-model.md). Each
decision is judged on its sources, not on what this repository's constitution already says.

## R0. What the machine checks, and what it does not

**Decision**: the audit checks **order**: every test new in the feature existed and did not pass
before the code that makes it pass. It does not check **strength** — that the test's assertions
tell right behaviour from wrong. Strength is measured by the project's mutation check at the story
review (R8).

**Rationale**: order is decidable from the worktree's history in any language; "failed for the
right reason" is not (R5). Böckeler's experiment found that "a red test tells you the agent ran it
and saw failure, not that the failure was for the right reason", and moved to mutation testing for
regression quality (martinfowler.com, 2026-08-10). Mutation testing measures strength directly,
including for a test that failed by assertion against a stub, which proves only that the assertion
tells the stub's value from the right one.

**Threat model**: an agent that takes shortcuts, not one that forges evidence. The agent can write
the ledger's ref and the hook settings; the audit does not defend against that, and the README says
so. ImpossibleBench (arXiv 2510.20270) shows agents editing tests to pass, so the audit does detect
the observable form of that: a test changed in the call that turned it green (R5,
`rewritten-to-green`).

## R1. Observe the worktree's state, not the agent's commands

**Decision**: a Claude Code `PostToolUse` hook on every tool records the worktree's state after each
call.

**Rationale**: what matters is which files a call changed, whatever wrote them. In the renta run
that motivates the feature, the mixed writes came through shell heredocs and `python3 - <<EOF`, not
the file-editing tool. `PostToolUse` fires for every tool, subagents included, and passes
`session_id`, `agent_id` and `cwd` (Claude Code hooks reference).

**Alternatives considered**:
- Parse each Bash command for the files it writes: unsound. spec-gates v0.4.0 spends 1,347 lines on
  it in `validate-bash.sh` and still allows a `python3 - <<'EOF'` that writes source and test (probe
  run 2026-10-07).
- Block writes before they happen (`PreToolUse`), as TDD Guard and Probity do: the verdict is a
  language model's, and TDD Guard's own `docs/enforcement.md` warns that shell writes bypass it
  unless shell commands are denied (Probity can block `sed`/`echo >` with `forbidCommandPattern`).
- Judge each action with a language model against the transcript (Probity): a verdict that is
  still a model's, a turn of tokens per action, and the transcript is written asynchronously and
  can lag the current turn (hooks reference).
- Claude Code's checkpoints: "Checkpoints only track changes made through Claude's file editing
  tools. Changes made through Bash commands or external processes are not captured"
  (code.claude.com/docs/en/best-practices) — blind to exactly the writes L1 found.
- Read the session transcript afterwards: it holds commands, not their effects on files.
- **The branch's commits as the records**, with no hook: replay each new test at the first commit
  that contains it. It needs nothing installed and no latency per call, but a commit holds many
  calls — in L1 the test and its code were written by separate calls and committed together, so
  commit granularity cannot tell test-first from code-first — and it gives no feedback at the
  call that went wrong. Lost on both counts.

Parallel tool calls: whether Claude Code runs write tools concurrently is not stated in its docs
(read 2026-10-07; not tested here). If two calls overlap, or a second call finishes before the
first call's hook takes its snapshot, their changes land in one record under the first call's name.
Judging them together fails closed — a test and its code written concurrently were not written in
order — and concurrent writers are outside the supported workflow (FR-016).

## R2. The ledger is a chain of commits under a per-worktree ref

**Decision**: each record is `git commit-tree <tree> -p <previous record>` with a JSON message
naming the time, session, subagent, tool, call, branch and HEAD commit;
`refs/worktree/test-first/ledger` points at the newest. The tree comes from a temporary index seeded
from the worktree's own index, `git add -A`, `git write-tree`. A call that leaves the tree unchanged
adds no record. The ref moves with `git update-ref <ref> <new> <old>`, retried on a race.

**Rationale**: reachable objects survive `git gc`; `refs/worktree/` is per worktree by git's
definition, so a linked worktree keeps its own ledger and removing the worktree removes it;
`update-ref` with the old value is atomic; `git log refs/worktree/test-first/ledger` inspects it.
Measured on a clone of renta (861 tracked files, git 2.55.0): 0.03–0.04 s per snapshot.

What it stores: the tracked and untracked-but-not-ignored files, as they are on disk — a faithful
state, because a replay needs the support files a test reads (fixture data, a new conftest), not
only paths the configuration names. Those objects stay in the local repository. A plain `git push`
does not send `refs/worktree/…`; `git push --mirror` does (both observed 2026-10-07, git 2.55.0).
The README says so.

**Alternatives considered**:
- A JSONL file plus loose tree objects: unreachable objects are pruned by gc after two weeks by
  default (`gc.pruneExpire`), so a long feature would lose its early births.
- `git stash create`: records the index as well as the worktree, and a stash commit's shape is not
  a plain tree to diff.
- One ref per record: thousands of refs slow every ref operation and clutter `git log --all`.
- One ref per branch: a branch created mid-session (`git checkout -b`) would start an empty chain
  and lose the uncommitted work it carried; one chain with the branch in each record keeps it (R12).
- An index kept between calls instead of seeded each time, so untracked files are not rehashed:
  0.03 s both ways on renta's clone (four and three runs). Not adopted; the trigger to revisit is a
  repository whose untracked, non-ignored files make a snapshot exceed SC-003.
- Snapshot only paths matching the test and source patterns: cheaper and stores less, but a replay
  would miss untracked fixture data outside both, and a test that needs it would fail at birth —
  a false red. Rejected for that false pass.

## R3. Python standard library for the hook and the audit

**Decision**: `ledger.py` and `audit.py`, standard library only, run as `python3 <path>`.

**Rationale**: the hook reads JSON on stdin and the audit parses JUnit XML; both are in the
standard library. Spec Kit's scripts already need `python3` once a preset is installed. The preset
install drops the executable bit (specify 1.1.0), so scripts are run through their interpreter.

**Alternatives considered**: bash with `jq` — the Stop-gate hook was written to need no `jq` at run
time, and XML in bash is not credible.

## R4. Telling the agent: exit 2 with stderr

**Decision**: when a call changed test and source files, or a record could not be made, the hook
exits 2 with a message on stderr. The message is conditional: it names both groups of files and
says that a test added or changed in this call together with the code that satisfies it will fail
the audit, so a symbol rename or a formatter run reads as information, not as an accusation.

**Rationale**: for `PostToolUse`, exit 2 shows stderr to Claude and cannot block, since the tool has
already run (hooks reference) — FR-004 and FR-005 exactly. The hook cannot know at that moment
whether a test was born in the call (that takes a replay), so it reports what it knows; the audit
decides.

**Alternatives considered**: `hookSpecificOutput.additionalContext` in JSON on stdout — equivalent
reach, more surface; kept as the fallback if exit-2 behaviour changes. Firing only when a test file
gained lines: still cannot tell a new test from an edited one without running it, and adds a diff
parse per call.

## R5. The audit applies fail-to-pass at each test's birth

**Decision**: for every test new since the base, the audit finds the record where it last appeared
(its birth) and the first record from there where it ran (not skipped). It is **red** when that run
did not pass and, at the record where it first passed, the test side as it stood just before that
record passes against that record's code. A test whose first run passed is accepted only if its
behaviour predates the feature (passes against the base's sources) or it replaced feature tests in
a call that is not two-sided (`refactored`, R13); otherwise it fails the audit.

"Did not pass" is any outcome but passed and skipped: a failure or an error. The audit does not
try to tell an assertion failure from an exception (R0): measured on pytest 9.1.1 (2026-10-07), a
missing method, an exception inside the code under test, a stub raising `NotImplementedError`, a
wrong call signature and an import inside the test body all produce `<failure>` with no `type`
attribute, only a message. A classifier would be one parser per runner and would still misjudge
the case Kiro's bugfix flow treats as valid red — an `AttributeError` that *is* the bug
(kiro.dev/blog/bug-fix-paradox, 2026-02-19).

**Rationale**: this is SWE-bench's FAIL_TO_PASS criterion — a test validated as encoding a change
fails before it and passes after (arXiv 2310.06770) — applied at the moment each test was written,
and it is the order Canon TDD describes: write the test, run it, see it fail ("perhaps it won't
even compile"), then make it pass (Kent Beck, newsletter.kentbeck.com/p/canon-tdd). Every framework
in L3 asks for this order; none observes it.

The green check closes the gap the first version left: a test born red as a stub and rewritten
together with its code in one call would have counted as red. At the record where the test first
passes, the test side as it stood just before — every test file and support file, not only the
test's own file — must pass against the new code. That proves the code satisfied the tests that
were written first. It also catches the shortcut ImpossibleBench documents — editing a test, or the
helper or case table holding its expected value, until it passes — when it happens in the call
that turns the test green. The test's file is run at every record from its birth until it first
passes (usually one or two records), so that call is found exactly.

Replays swap whole sides — the test side from one record, everything else from another — and never
only the files matching the source globs: code written first in a template, a schema or fixture
data outside `tests` would otherwise stay in a "base" tree and make a later test look as if it
predated the feature (second review, 2026-10-07).

**Alternatives considered**:
- Fail-to-pass once per pull request against the base, as robot_sf's CI catcher does (L9): blind
  to order — code written first still fails at the base — and it accepts any test that calls a new
  symbol, since that errors at the base.
- Accept an `ImportError`/`AttributeError` red only after a stub (the first version, and Kiro's TDD
  hook): undecidable from JUnit in pytest, as measured above, and a stub-red still proves no
  strength; mutation testing does (R0, R8).
- Keep the agent's red record in `tasks.md`: it is the defect observed.
- Accept a test born green from a test-only call: leaves code-first open one call apart.
- Overlay only the source globs onto the base, or revert only the test's own file before the green
  record (the first revision): both let a change outside those paths through, as above.

## R6. Test identity and outcomes from JUnit XML, one file per run

**Decision**: the project's configured command runs one test file and writes JUnit XML; a test is
`classname` + `name` of a `testcase`; its outcome is failed (a `failure` or `error` child), skipped
or passed. A run that writes no JUnit, or whose cases all failed and match exactly what the same
command reports on the same tree with that file replaced by unparseable bytes (the load probe), is
*inconclusive*: it says nothing about which tests exist, so presence is carried over from the last
conclusive run. A run with no case at all is conclusive: the file has no tests.

**Rationale**: the one result format pytest, Jest (jest-junit), Vitest and PHPUnit all write for a
single test file (pytest's and Vitest's measured, Jest's and PHPUnit's not), so the audit stays
language-agnostic. Go writes it through gotestsum, but its unit is the package, not the file, so Go
is not supported. One file per run because a collection error in one file stops pytest from running
the others (measured, pytest 9.1.1, without `--continue-on-collection-errors`), and a replay must
not let one file hide another. Inconclusive runs are carried over so that a typo that breaks a file
for one call does not end the stretch of records in which its tests exist, which would make them be
born again later. Runners disagree on how a load failure looks (L7, measured 2026-10-07): pytest
9.1.1 reports one `<error>` case named after the module with an empty classname, the same for a
syntax error and an import that does not resolve, and writes no case at all for a file without
tests; Vitest 5.0.3 reports one `<failure>` case named after the file path for a syntax error, an
unresolved import and a file without tests alike. A rule written from one runner misreads the other,
so the shape is measured at the moment it matters, on the same tree and file, and only when a run's
cases all failed. Measuring at each run also survives a runner upgrade that changes the shape.
Because Vitest reports a file without tests like a file that cannot load, the redo sequence removes
the file when the test it removes is the file's only one.

**Alternatives considered**: parsing test sources (one parser per language); `pytest
--collect-only` (pytest only); "inconclusive when every case erred" (the first version: pytest's
shape only — under Vitest a typo would end its tests' stretch and they would be born again green);
"inconclusive when the run shares no test with the file's last run" (misreads a call that replaces
every test of a file with new failing ones); a table of known runners in the audit (a release of
the preset for every runner, and wrong as soon as a runner changes its report); the installer
measuring the shape once (the first revision: stale after a runner upgrade, and its path template
breaks where pytest's rootdir is not the repository root).

## R7. Replays in one isolated worktree, cleaned, bounded and checked for isolation

**Decision**: the audit adds one detached scratch worktree, moves it to each tree it needs with
`git read-tree -u --reset <tree>`, runs `git clean -fdx` before every run, and runs the command
through `run-bounded.sh` with a deadline. The command may name `{root}`, the real worktree, to
reuse its installed environment. Every test whose first run passed must **not pass** when every
source file is removed from the tree before it can be accepted (`predates`, `refactored`): that
proves the run reads the scratch tree's sources and not the real worktree's.

**Rationale**: a run must see the record's files and nothing else: in renta a same-size edit within
the same second reused a stale `.pyc` and three false failures followed (tasks.md of feature 001,
T004); `git clean -fdx` removes every untracked cache in any language. A replay of a wrong record
can hang, and constitution IV requires a deadline that kills the process group. Reusing `{root}`'s
environment is a real hazard — an editable install (`.pth`) or a workspace link points imports at
the real worktree, as the implement fragment's review section already records — and its failure
direction is the dangerous one only where a pass is accepted; the source-removal run checks exactly
those cases and costs one extra run per accepted-green test.

Cost: `git clean -fdx` turns every replay of a compiled project into a full build. SC-004's budget
is stated for pytest; for compiled languages it is not measured, and the README says so.

**Alternatives considered**: a fresh clone and environment per record (seconds to minutes each);
replaying in the real worktree (destroys uncommitted work); a global isolation probe with a planted
syntax error (language-specific, and says nothing about the specific runs that accept a pass).

## R8. The story review uses the project's mutation check

**Decision**: where the project's constitution or CI names a mutation check, the reviewer runs it
over the story's changes and treats each survivor as a test gap or a justified exception;
otherwise the reviewer writes wrong versions by hand, as in 1.x.

**Rationale**: mutation testing is the oracle Böckeler recommends for regression quality, and
reporting mutants on the code under review is Google's practice (Petrović & Ivanković, ICSE-SEIP
2018; cited from secondary sources, not reopened). renta gained such a gate on 2026-10-07
(`scripts/mutation_gate.py`), which ran in 35–55 s for one touched method.

**Alternatives considered**: shipping a mutation tool in the preset — tools are per language, and
the project already knows its own.

## R9. Property cases for stated invariants

**Decision**: when the spec states an invariant (conservation, ordering, a bound), the implementing
task's test list includes a property case over generated inputs.

**Rationale**: Kiro derives correctness properties from EARS requirements and runs them as
property-based tests (kiro.dev/docs/specs/correctness, updated 2026-08-04; property-based testing is
marked available in Kiro's IDE only), and on a failing property offers to fix the code, the spec
or the test. Anthropic's agentic property-based testing found valid bugs in 56% of its reports
across 100 Python packages, 86% of its top-ranked ones (arXiv 2510.09907) — evidence that
properties find real bugs, not a measurement of property cases inside a test-first list, so this
rule is directional until a feature measures it. The cases go through the audit like any test: a
property born green fails (Kiro's own page warns "A property that is too weak … will pass while the
real behavior is still wrong").

**Alternatives considered**: property cases for every task — no evidence of value where no
invariant is stated, and it inflates lists. Kiro's optional, test-after property tasks (L3):
contrary to the order this preset exists for.

## R10. Rules removed, and what was not adopted

**Removed from `speckit-implement`**: recording the red run under each case, and accepting a test
that passed on its first run by breaking the code on purpose. Evidence: renta feature 001 on 1.6.0,
27 of ~60 cases recorded as first-run passes, 11 test runs from one call writing code and test
together — one feature, so directional. The redo sequence replaces the break-on-purpose route: it
is the same act, observed by the machine instead of narrated.

**Not adopted**:
- A separate agent writing tests: the only direct comparison found no gain at 3–8.5 times the
  tokens (Böckeler; n=2 per arm, directional).
- An LLM-judged guard on every write (Probity, TDD Guard): R1.
- Code-writing subagents in worktrees of their own: each worktree's ledger is removed with it, so
  the tests merged back would be unobserved (R14). The fragment keeps writers in the feature's
  worktree, one at a time.
- Pushing the ledger so CI can run the audit: the records hold uncommitted and untracked files,
  which a project may not want on its remote, and CI would need each record's environment as the
  local audit does. The guarantee stays local, at the Stop hook and the story close (R12); a
  project that wants it remotely can push `refs/worktree/…` itself.

## R11. Python toolchain for this repository

**Decision**: `pyproject.toml` with a uv dev group (ruff, mypy, pytest, pytest-timeout),
`[tool.uv] package = false`, `uv.lock` committed, mypy strict over `scripts/python` and
`tests/python`; CI runs ruff, mypy and pytest. Both files are export-ignored.

**Rationale**: the global rules' approved defaults for a Python project; the repository had no
Python before this feature, so the toolchain lands as its own task.

**Alternatives considered**: `unittest` without dev dependencies — no linter or type checker, which
the global rules require of Python code.

## R12. One audit, two entry points, over the branch's own history

**Decision**: the audit searches the branch's effective history (data-model.md) back from the newest
record for each new test's birth, then forward from the birth, and every replay it runs is memoized
by the tree it ran on, the file and the configured command. It runs at two points: a `Stop` hook at
the end of every turn, within a time budget, which blocks the turn once when a test present in the
newest record has a final failing verdict (born with its code, born green, rewritten to green); and
at the close of each story, without a budget, for the full report the reviewer receives. Both
snapshot the worktree first, so edits made between calls are judged too. The range is not a time:
births are found from the records themselves, and the base only decides which tests are new.

**Rationale**: an audit the agent must remember to run is the prompted check every framework in L3
already has. A Stop hook is the deterministic gate Claude Code's best practices name for an
unattended run ("a Stop hook runs your check as a script and blocks the turn from ending until it
passes"). This one blocks once per turn and lets the next stop through, as the preset's Stop gate
does: ImpossibleBench found a way out (`flag_for_human_intervention`) cut cheating from 54% to 9%
for GPT-5, and a gate with none is the pressure under which agents edit tests. So the Stop hook
guarantees the agent is shown a failing verdict every turn, not that the turn cannot end with one;
the story-close audit, which the fragment runs, is the full report. Every failing verdict that is
final has a remedy: the redo sequence for a test written with or after its code, the configuration
for one that passes without any source; so no exception list is needed. The memo makes the Stop run
incremental without a second algorithm: a turn pays for replays of its own records, until the base
moves (a rebase), after which base runs are made again. An environment change does not invalidate
the memo (data-model.md, Memo). Searching back from the newest record bounds the work to each test's
own history, so a long-lived ledger does not make older features' records replay. A run that wrote
no JUnit is not memoized, since a broken installation rather than the tree may be the cause. The
effective history follows the branch across `checkout -b`, renames, visits to other branches and
rebases, which a clock-based range does not: rebasing onto a newer main moved the base's time past
the feature's early records.

**Alternatives considered**:
- The story-close audit alone (the first version): prompted, so skippable.
- A git `pre-push` hook: deterministic, but after the fact, and `--no-verify` skips it.
- An audit state saved between runs instead of a replay memo: a second code path, and state to
  invalidate whenever the base or the configuration changes; the memo is keyed on content and needs
  no invalidation.
- A fold forward from the origin (the first revision): replays a changed file at every record of
  every earlier feature in the same worktree, with today's environment.
- Running replays in several scratch worktrees in parallel: not adopted until the cold audit of
  SC-004 is measured; the trigger is a cold audit over 15 minutes.

## R13. Renamed and consolidated tests

**Decision**: a test whose first run passed is `refactored` — accepted, and listed with the tests it
replaced — when it fails without the sources (R7), its record's change is not two-sided
(data-model.md, Change: test-side paths and any other path), accepted tests of the feature
disappeared at the same record (from a test file that record changed, or from its own file when the
record changed no test-side path, as when an enum rename renames parametrized ids), and the tests
whose first run passed at that record are no more than those that disappeared. When more appear,
none is refactored, and the fragment tells the agent to split a rename from a new test.

**Rationale**: the implement fragment's refactor step renames, moves and consolidates tests;
identity by name made each of those a `born-green` failure in the first version. A count is
mechanical, language-agnostic and needs no replay against older code. The only way past it is to
delete an accepted test in order to add an untested one, which is forging evidence, outside the
threat model (R0). A two-sided call is excluded because rewriting an accepted test together with the
code for a new case is the defect L1 observed, under another name (fourth review). A test that comes
back with its file exactly as it was when accepted — a stash and pop, an undone rename — keeps its
verdict (data-model.md, Restored), so honest round trips cost nothing.

**Alternatives considered**:
- Any passing test in a test-only call that removed an accepted one (first revision): one rename
  carried any number of unrelated new tests (second review).
- The new test must fail before and pass after the replaced test's driving code change (second
  revision): an honest rename failed whenever its file had since come to import a later symbol or
  call a changed API, because the old code no longer loads it (third review). Replaying against
  older code is the fragile part; the count needs none.
- Matching removed and added tests by body similarity: a parser per language.
- Accepting a rename only when it passes against the base: fails every rename of a test of new
  behaviour.

**Limit**: identity is the test's name, so changing the body of an already accepted test to cover
new code is not judged. The story review's mutation check measures that test's strength; the README
states the limit.

## R14. Imported tests and the base

**Decision**: a test whose birth is at a record whose HEAD moved to a commit that already contains
the test arrived with commits the ledger did not see written — a merge, a fast-forward, a pull, a
cherry-pick — and is `unobserved`. The base is the merge base with the remote-tracking default
branch (`origin/HEAD`, else `origin/main`, else `origin/master`), and with the local default branch
only in a repository without an `origin` remote; the audit refuses on the default branch itself;
the installer refuses when no base resolves. Nothing is fetched.

**Rationale**: tests the agent writes and then commits appeared in a record before the commit, so
only tests that came from elsewhere are born together with a HEAD that already holds them. Saying
`unobserved` about them is true; judging them on records of another line is what kept failing
review. A base taken from the local default branch moves when an agent merges locally — a shortcut,
not forgery — and empties the set of new tests; the remote-tracking branch moves only with a fetch
of a pushed change. Fetching to resolve it would be network access, which the preset's scripts do
not make.

**Alternatives considered**:
- Follow a merge into the merged line's records (second revision): records made on the merged
  branch before its first commit carry the fork's HEAD and fell outside the line, and a
  fast-forward makes no merge commit at all (third review).
- Keep the ledgers of removed worktrees under a shared namespace so their work can be followed: refs
  that outlive their worktrees and need pruning, for a workflow the fragment does not use; the
  trigger to revisit is a project that needs parallel code-writing worktrees.
- Record the base when the branch's line starts: survives a missing remote, but is wrong after a
  legitimate rebase onto a newer default branch.

---

# Landscape and evidence (2026-10-07)

The research behind R0–R14, kept whole so a later session does not redo it. Sources were read on
2026-10-07 unless dated otherwise. **Verified** = read in the primary source or measured here;
**second-hand** = from search results or a summary, not opened.

## L1. What motivated the feature: the renta run on preset 1.6.0

Project renta (private), feature `001-bridge-adjudication`, implemented 2026-10-06/07 with this
preset at 1.6.0 and Spec Kit 1.1.0. One feature: the numbers below are directional.

- `tasks.md`: 33 case bullets record a red run, 27 record "passed on first run" (grep of
  "passed on first run|passed against|passed first"), out of about 60 cases.
- Session transcript (Claude Code JSONL), analysed with a script that, for each Bash call running
  pytest, classified which files the same command wrote (test files `tests/…`, source `co/…`,
  detected by `cat >`, `p='…'` in `python3 - <<EOF`, `sed -i`, `printf >>`) and the run's outcome.
  Of the runs that wrote files: 22 test-only green, 20 code-then-test red, 15 code-only red, 13
  code-only green, **11 code-and-test (CT) green**, 9 test-only red, others below 5. Reading the 11
  CT-green commands: production code and its test written in one shell command, then run green —
  e.g. the `OneOf.nearest` tie rule with "a single option is its own nearest"; the DEFECT/KNOWLEDGE
  "exactly one side" rule with three tests ("10 passed"), recorded in tasks.md as "passed on first
  run (the side-count rule)". Verified.
- The 1.6.0 fragment allowed it: "A new test that passes on its first run has not been watched
  failing. Break the code it pins on purpose, watch the test fail for the expected reason, restore
  the code, and record that failure and that the behaviour already existed." It does not tell
  "existed before this task" from "written a moment ago". Verified.
- The agent edits through Bash heredocs and `python3 - <<EOF`, so any Edit/Write-only hook is blind
  to most writes. Verified in the transcript.

## L2. Spec Kit core (github/spec-kit v1.1.1, 2026-10-06)

- `spec-driven.md:312`, Article III: "This is NON-NEGOTIABLE: All implementation MUST follow strict
  Test-Driven Development. No implementation code shall be written before: 1. Unit tests are
  written 2. Tests are validated and approved by the user 3. Tests are confirmed to FAIL (Red
  phase)". It claims "The implementation template enforces test-first development"; no current
  template carries that order (grep of `templates/`).
- `templates/constitution-template.md`: TDD only as a commented example.
- `templates/tasks-template.md:12`: "Tests are OPTIONAL - only include them if explicitly requested
  in the feature specification"; also "Write these tests FIRST, ensure they FAIL before
  implementation".
- `templates/commands/implement.md`: "Execute test tasks before their corresponding implementation
  tasks".
- Issues: #627 "TDD principles not followed" (agent writes all tests, sees red, implements
  everything) closed NOT_PLANNED on 2026-05-04 by github-actions for 180 days of inactivity, not by
  a maintainer. #2634 "[Feature]: Add Test-Driven Development (TDD) Support to the Framework"
  (scaffolding failing test stubs) closed NOT_PLANNED 2026-08-04 by a collaborator: "Closing as
  there are multiple identified ways that you can use", after comments pointing at superpowers and
  d0whc3r/spec-kit-tdd.
- Extension hooks (`extensions.yml`, events `before_*`/`after_*`) are prompts: the agent is told to
  emit `EXECUTE_COMMAND:`. Nothing in core verifies red-before-green.
- Verified (primary repository, cloned; #627's closer checked with `gh issue view`).

## L3. Other spec-driven frameworks and agent tools

| Framework | Stance on test-first | Enforcement |
|---|---|---|
| **Kiro** (kiro.dev) | Feature specs: correctness properties extracted from EARS requirements, run as property-based tests ("PBTs are optional by default"; IDE only per the capability table, docs/specs/correctness updated 2026-08-04). Test tasks in generated `tasks.md` are optional (`*`) and follow implementation (second-hand: public repos' generated files). Bugfix specs: "Kiro runs every test against the unfixed code first, applies the fix, then retests"; a test that fails "for a different reason, or don't fail at all" refutes the hypothesis; preservation tests record the unfixed behaviour — "the unfixed code acts as the spec" (blog/bug-fix-paradox, 2026-02-19). An official "TDD: Test First" hook (Pre Tool Use, tool `write`, action Ask Kiro) requires "assertion failures" and calls a `ModuleNotFoundError` an "INVALID RED PHASE" (blog/how-tdd-should-feel, 2026-05-21). | All prompted: the agent runs the tests and documents the failure; nothing outside it checks. Command hooks can block Pre Tool Use and Prompt Submit (docs/hooks, updated 2026-09-30). No mutation, coverage or test-immutability gate found. |
| **OpenSpec** v1.14.1 | Core `spec-driven` schema: "Each task MUST state how to verify completion (a test, command, observable behavior, or delivered artifact)" (`schemas/spec-driven/schema.yaml:225`). The community `anvil` schema keeps a test plan that "doubles as a red/green ledger that `verify` audits"; of its review gate the docs say "OpenSpec only checks that artifacts exist, so enforce the gate with your own CI or hook" (`docs/customization.md:425`). | None in core. |
| **BMAD** v6.12.1 | Dev agent: "test-first discipline — red, green, refactor"; `bmad-dev-story` step 5: "Write FAILING tests first" and "Confirm tests fail before implementation - this validates test correctness". The separate Test Architect module (TEA v1.27.2, 2026-09-18) generates acceptance tests with `test.skip()`; "The developer un-skips one test, confirms it fails, then makes it pass." | Red prompted, never verified. TEA's `atdd-red-check.js` runs only in TEA's own eval harness. |
| **obra/superpowers** v6.4.2 | Iron Law: "NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST" and "Write code before the test? Delete it. Start over."; "Verify RED - Watch It Fail … MANDATORY. Never skip." | Only a `SessionStart` hook injecting context: prompt only. |
| **TDD Guard** v1.7.0 / **Probity** v1.10.1 (nizos) | TDD Guard "grew into Probity" and remains maintained. Probity: PreToolUse on `Bash|Write|Edit|NotebookEdit`; `enforceTdd` "Uses an AI validator — via the agent's official SDK — to judge the pending action against the transcript and the file's current content"; opt-in fast path for a write that "adds exactly one new test node"; `forbidCommandPattern` can block `sed`/`echo >`; fails closed without config; supports Claude Code, Codex and Copilot CLI; the user can override a verdict in-session. TDD Guard's `docs/enforcement.md`: shell commands modify files "without triggering TDD validation" unless denied. | Trigger deterministic, verdict a model's. npm (`tdd-guard`, `@nizos/probity`) + TypeScript config. |
| **Gemini Conductor** v0.3.0 | Default `workflow.md`: "Test-Driven Development: Write unit tests before implementing"; "CRITICAL: Run the tests and confirm that they fail as expected… Do not proceed until you have failing tests." Plans put "Write Tests" before "Implementation". | Prompt only; the workflow is an editable template. |
| **cc-sdd** v3.1.0 (gotalab) | Implementer: "RED: write/adjust tests so they fail with the flag OFF. Run tests and capture the failing output"; status must carry `RED_PHASE_OUTPUT`. | A reviewer subagent checks the report "includes `RED_PHASE_OUTPUT`": pasted text from the agent. |
| **Taskmaster** autopilot v0.43.1 | RED→GREEN→COMMIT state machine; "RED phase must have at least one failing test"; with 0 failures in RED the "subtask auto-completes". | Counts supplied by the agent; Taskmaster runs nothing. A test born green is accepted. |
| **GSD** v1.50.0-canary.0 | `references/tdd.md`: "Run test - it MUST fail". `tdd_mode` reported off by default (second-hand: the cited config line was not found here). | An "MVP+TDD gate" greps `git log` for a `test(...)` commit; blocks only with both MVP and TDD modes on; never runs the test. |
| **truenorth-mcp** v1.0.4 | `truenorth_tdd_cycle` "enforce[s] the red-green-refactor order". | The tool runs the red command and rejects exit 0 (`runtime/src/tools/tdd.rs`) — but the agent names the command, any non-zero exit counts, and it is a live run, not a replay of history. |
| **Aider** | `--test-cmd`/`--auto-test`: "Aider will try and fix any errors if the command returns a non-zero exit code." | Green loop, no order. |
| **Cursor** | Hooks `preToolUse`, `postToolUse`, `afterFileEdit`, `beforeShellExecution`, `stop`, `subagentStop`…; exit 2 blocks, other exits fail open unless `failClosed: true`. | No TDD mechanism. |
| **OpenAI Codex** | Hooks PreToolUse (can deny), PostToolUse ("including Bash, `apply_patch`, MCP tool calls"), Stop (can continue) — learn.chatgpt.com/docs/hooks. | No test-first mechanism; the ledger's hook would port. |
| **Copilot** | Coding agent: "run tests and linters", hooks for validation, no TDD mechanism. VS Code guide: TDD-red, TDD-green and TDD-refactor custom agents, a human reviews the red tests at handoff. | Prompt plus human. |
| **Claude Code** | Best practices: "have one Claude write tests, then another write code to pass them"; "write a failing test that reproduces the issue, then fix it"; hooks "are deterministic and guarantee the action happens"; a Stop hook "as a deterministic gate"; a verification subagent "so the agent doing the work isn't the one grading it". | Mechanisms, no TDD policy. |
| **Agent OS** 3.0, **spec-workflow-mcp** 2.2.7, **Tessl** | No TDD workflow (spec-workflow-mcp lists test tasks after implementation; Tessl's docs index has no TDD entry). | None. |

Verified except where marked; Traycer, Zencoder, Windsurf, Junie, Augment, Amp, Factory, Cline/Roo
and Antigravity showed nothing test-first-specific in searches (second-hand).

## L4. Spec Kit community extensions evaluated (cloned, read in full)

- **d0whc3r/spec-kit-tdd v1.1.2** (5 stars, four releases all 2026-08-03): package is
  `extension.yml`, README, LICENSE, four prompt commands and four templates — **nothing executed**
  beyond Spec Kit invoking `before_implement: speckit.tdd.run`. Its rubric grades PROVEN when "the
  cycle log records the red command and its failure output" — the agent's own log — and "A commit
  that adds a source file and its test in one commit is normal". Its Phase 3 prescribes the same
  "break the implementation … confirm the test fails, then restore" route. Mutation testing is
  advice, gated by the agent's own verdict. Rejected.
- **schwichtgit/spec-gates v0.4.0** (3 stars, released 2026-10-06): real bash hooks with exit codes
  — protect-files (PreToolUse Write|Edit), validate-bash (PreToolUse Bash, 1,347 lines of regex),
  validate-pr, post-edit formatting, Stop `verify-quality.sh`, git hooks, CI projection, "canaries"
  (15 planted violations each gate must reject), attestations. **No red-before-green and no
  mutation testing.** Probes: `python3 - <<'EOF'` writing `src/calc.py` and `tests/test_calc.py`
  → allowed (rc 0); `sed -i` on source → allowed. Its 1,092 hook tests passed here (4m09s). Default
  commit rules block "Anthropic" and `\bClaude\b` (would reject Co-Authored-By lines). Rejected;
  ideas borrowed: canaries, and observing tree state instead of parsing commands.

## L5. Evidence on TDD with agents

- **Böckeler, "TDD inside the agent loop – theater or actual value?"**
  (martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html, 2026-08-10): three
  greenfield Python tasks, Sonnet 4.6 generating, Opus 4.8 judging, n=2 per arm (6 for medium TDD) —
  directional; "more than once Opus ranked the non-TDD workflow solutions slightly higher in design
  and test quality"; "no meaningful difference in mutation scores"; tokens 8.50× (small), 2.96×
  (medium), 4.89× (large), overstated by cache reads per the author; "agents still sometimes skipped
  or faked the red step, or implemented ahead of the test so that it passed immediately"; she
  focuses on "monitors and improves regression quality with the help of mutation testing, instead
  of giving elaborate TDD instructions". Verified.
- **arXiv 2607.05139** (Konstantinou, Tambon, Papadakis, July 2026): tests generated after faulty
  code detect fewer faults than tests generated independently, 14% vs 25% — error propagation.
  What it measures is independence of the test from the code; the audit enforces order, which is
  necessary for independence but does not prove it (a test can be written after code was drafted
  outside the worktree).
- **Mathews & Nagappan, arXiv 2402.13521**: tests in the prompt +12.0 (GPT-4, MBPP), +8.5
  (HumanEval), +29.6 (Llama 3, MBPP).
- **TiCoder, arXiv 2404.10100**: test-driven intent clarification, +45.97% pass@1 within 5 user
  interactions (idealised user).
- **TDD-Bench Verified, arXiv 2412.02883**: 449 issues; TDD tests defined as fail-to-pass.
- **SWT-bench, arXiv 2406.12952**: generated reproduction tests double SWE-Agent's precision as a
  filter.
- **ImpossibleBench, arXiv 2510.20270**: cheating on Conflicting-SWEbench GPT-5 54%, Opus 4.1 50%;
  hiding tests cuts it to near zero; read-only tests particularly effective against Opus 4.1,
  whose main strategy is modifying tests; a `flag_for_human_intervention` exit cut GPT-5 54% → 9%
  (much less for Opus 4.1); LLM monitors caught 42–65%.
- **Agentic PBT, arXiv 2510.09907** (Maaz, DeVoe, Hatfield-Dodds, Carlini; Anthropic): 100 Python
  packages, 56% of reported bugs valid, 86% of the top 21; 3 merged patches incl. NumPy.
- **Meta ACH, arXiv 2501.12862**: mutation-guided test generation, 10,795 classes, 9,095 mutants,
  571 tests, 73% accepted by engineers; equivalent-mutant detector precision 0.79 / recall 0.47
  (0.95 / 0.96 with pre-processing).
- **Kent Beck, Canon TDD** (newsletter.kentbeck.com/p/canon-tdd): one case at a time from a test
  list that grows; turning the whole list into tests up front is a mistake; a new test may fail by
  not compiling.
- **Petrović & Ivanković, "State of Mutation Testing at Google"**, ICSE-SEIP 2018: mutants surfaced
  at code review on the changed code, not as a codebase score. Second-hand (cited, not reopened).

## L6. Deterministic checks that a test encodes new behaviour

- **SWE-bench, arXiv 2310.06770**: "we apply the PR's test content, and log the associated test
  results before and after the PR's other content is applied. We filter out task instances
  without at least one test where its status changes from a fail to pass"; it also excludes
  instances "with tests that invoke newly created functions". SWE-bench uses this to select
  benchmark tasks; the criterion, not the purpose, is what R5 borrows.
- No authoritative ready-made CI action for fail-to-pass was found; the closest is robot_sf's
  catcher (L9).
- **Mutation tools for Python**: mutmut 3.8.0 (2026-09-12) — no diff mode, function-name globs
  (`mutmut run "module.func*"`), re-tests only functions whose source changed when `mutants/`
  persists, skips decorated functions other than a lone `@staticmethod`/`@classmethod`, and
  `__new__`/`__getattribute__`/`__setattr__`; statuses from `mutmut.stats.status_by_exit_code`
  (killed, survived, no tests, not checked, suspicious, skipped, timeout, caught by type check,
  segfault, check was interrupted by user). cosmic-ray 8.7.0 — `cr-filter-git` restricts to edited
  lines. pytest-gremlins 1.11.2 — content-hash cache, no diff flag. mutatest — no release since
  2022.

## L7. Measurements made in this session

- **Whole hook cost** (T008, `tests/ledger.sh`, 2026-10-07): `python3 ledger.py` with the hook JSON
  on stdin, after a one-file change, on a scratch repository of 1,001 tracked files and no untracked
  ones; Python 3.14.7, git 2.55.0, macOS on Darwin arm64 (Mac16,8). First version (ten git
  processes): median 99 ms of five. After cutting to eight git processes on a record and five on an
  unchanged tree, and a `NamedTuple` instead of a dataclass (no `inspect` import): medians of 80–83
  ms of eleven over three runs, single calls 58–110 ms at a load average of 3.2. Profile: Python
  start 11 ms, imports 13 ms, snapshot (`add -A` + `write-tree`) 25 ms, each other git process
  about 5 ms.
- **Racy git and the snapshot's index copy** (T006/T020, 2026-10-07, git 2.55.0, macOS): git
  trusts an index entry's stat unless the entry is not older than the index file. Copying the index
  with a fresh mtime disables that recheck: a same-size edit made in the second the index was
  written, with the snapshot starting in the next second, was missed 10 times of 10; keeping the
  index's mtime (`shutil.copy2`) missed 0 of 10. At unforced timing, 1 of 300 against 0 of 300.
- **Ledger snapshot cost**: temporary index copied from the worktree's, `git add -A`,
  `git write-tree`, on renta (860 tracked files): 0.04–0.05 s, three runs. Repeated on a fresh clone
  (861 files, git 2.55.0): 0.03–0.04 s seeded each time (three runs), 0.03 s with an index kept
  between calls after a 0.20 s first run (four runs).
- **Per-worktree refs and push**: `git push <remote> main` sent only `refs/heads/main`; `git push
  --mirror` also sent `refs/worktree/test-first/ledger` (git 2.55.0, scratch repositories).
- **pytest 9.1.1 JUnit** (`--junitxml`, one scratch project): an assertion, a missing method, an
  exception inside the code under test, a stub raising `NotImplementedError`, a wrong keyword
  argument and an import inside the test body all give `<failure>` without a `type` attribute; a
  failing fixture gives `<error message='failed on setup with …'>`; a module-level import of a
  missing name gives one `<error message='collection failure'>` test case named after the module
  and, without `--continue-on-collection-errors`, no results for the other files of the run.
- **Vitest 5.0.3 JUnit** (`--reporter=junit`, node 26.7.0, one scratch project): every failure is
  `<failure>` with a `type` attribute — `AssertionError` for an assertion, `TypeError` for a missing
  method and for a crash inside the code under test, `Error` for a stub that throws; a skipped test
  is `<skipped>`; a file whose import cannot resolve gives one `<failure type="Error">` case whose
  classname and name are the file's path. So Vitest exposes a type where pytest does not, and the
  two report a file that cannot load differently.
- **Probe environment**: pytest 9.1.1 on Python 3.12.12 (`uv run --no-project --with pytest`);
  Vitest 5.0.3 on node 26.7.0 (pnpm); macOS (Darwin 27.0.0); 2026-10-07.
- **A test file that does not exist**: pytest 9.1.1 exits 4 and writes JUnit with `tests="0"` and no
  case; Vitest 5.0.3 writes JUnit with `tests="0"` and no case.
- **pytest 9.1.1 and Vitest 5.0.3, load failures and empty files** (same scratch projects): pytest
  reports unparseable content in a test file exactly as a missing import, one `<error
  message="collection failure">` case named after the module, and a file without tests as
  `tests="0"` with no case. Vitest reports unparseable content, an unresolved import and a file with
  no test alike: one `<failure type="Error">` case whose classname and name are the file's path.
- **Claude Code hooks reference**: PostToolUse fires for subagents' tool calls with `agent_id`;
  exit 2 shows stderr to Claude and cannot block; matcher `*` matches every tool;
  `${CLAUDE_PROJECT_DIR}` stays at the original root, read `cwd` for worktrees; the transcript is
  written asynchronously and can lag; "All matching hooks run in parallel"; command hooks default
  to a 600 s timeout, settable per entry with `timeout`: "Seconds before canceling"; "Claude Code
  cancels a `command`, `http`, or `mcp_tool` hook that reaches its `timeout`, discarding the hook's
  output, so on most events a timed-out hook renders no decision" (an earlier WebFetch summary had
  reported milliseconds, which is the Bash tool's `timeout`; corrected from the page's source,
  `code.claude.com/docs/en/hooks.md`); the Stop input carries `stop_hook_active`, "`true` when
  Claude Code is already continuing as a result of a stop hook"; "after stop hooks have continued
  the turn eight times in a row, Claude Code overrides the next block and ends the turn", and "The
  count of consecutive continuations resets each time Claude calls a tool". Read 2026-10-07
  (code.claude.com/docs/en/hooks).
- **renta mutation gate** (merged 2026-10-07, PR #59, `scripts/mutation_gate.py`): on renta main
  a7503cd, mutmut over all of `co/` with the 40 runnable `tests/co` files: 3,589 mutants, 2,653
  killed, 936 survived; of the survivors 593 message-only (AST rule), 322 behaviour, 21 not
  classified by the prototype. All of `co/` under the ci Hypothesis profile: 4.5 min wall, 28 min
  CPU; one touched method: 35–55 s. Three independent reviews found and closed: fail-open on
  statuses other than `survived`, a shared allowlist that broke the weekly run, "message" too
  broad (nested text, stored arguments), `async def` unread, deleted files misattributed. Python
  3.14 also surfaced SyntaxWarnings in `formulas` 1.3.4 (`v is 1.0`, `v is not ""`), fixed upstream
  in vinci1it2000/formulas#184 (open).

## L8. Synthesis

Practitioners and data converge: test-first order cannot be prompted into reliability — every
framework in L3 prompts it, and the ones that "check" it check the agent's own report (pasted red
output, supplied counts, a commit message) — and Böckeler and Spec Kit #627 saw it faked. What buys
fault detection is a test independent of the code plus a mechanical oracle for strength. Prompts
carry intent — the case list, the properties from the spec, a stop-and-report exit. The machine
carries the checks: observe the tree (not the commands), apply fail-to-pass at each test's birth
and at the call that turns it green (this feature), and measure strength with mutation testing on
the changed code (renta's gate). Not worth adopting: an LLM judge on every write, micro-step
ceremony (3–8.5× tokens, no measured gain), whole-repo mutation on every change, red logs the agent
writes itself, and a classifier of failure reasons that the result format cannot support.

## L9. Prior art closest to the audit (searched 2026-10-07)

Nothing found records the worktree per tool call and replays each test where it was born.

1. **robot_sf "CI catcher"** (ll7/robot_sf_ll7 issue #9986, opened 2026-09-29, closed): for a pull
   request, runs tests "new (or whose body changed) relative to the merge base" against "the base
   production code with the head's tests" and reports each that passes there as "does not detect
   its regression"; advisory first, "precision measured on >= 10 recent merged PRs" before
   blocking; "an ImportError/AttributeError counts as 'fails on base'". Our `predates` check, per
   pull request, blind to order. Verified (issue text; the PR's code not read).
2. **SWE-bench / SWT-bench / TDD-Bench Verified harnesses**: a harness, not the agent, runs each
   test before and after a known fix — the criterion R5 applies, offline, against a golden patch.
3. **truenorth-mcp `tdd_cycle`**: the only shipped agent tool found that runs the red itself;
   agent-chosen command, any non-zero exit, live rather than replayed (L3).
4. **GSD's MVP+TDD gate** and **Taskmaster's autopilot**: history or state checks over what the
   agent reports; nothing is executed.
5. **cyber-dojo traffic lights** (blog.cyber-dojo.org, 2014): every test run recorded and
   versioned as red, amber (did not run) or green — the human-kata ancestor of the ledger, with
   "did not run" kept apart from red, as R6's inconclusive runs are. Second-hand.

Considered and not close: TDAD (arXiv 2603.17973, test-impact graphs), GTDD (arXiv 2610.02952,
hidden audit of an implementation snapshot, not of test order), gentle-ai #3727 (verifier-chosen
fault injection, closed not planned), matatk/tdd-bdd-commit (archived; red/green commit order only).
