# Data Model: Observed test-first

## Configuration — `.specify/test-first.json` (committed)

| Field | Type | Rule |
|---|---|---|
| `tests` | list of globs | Non-empty; matches at least one tracked file at install (FR-014) |
| `sources` | list of globs | Non-empty; a path matching both `tests` and `sources` counts as a test |
| `run` | string | Contains `{file}` and `{junit}`; may contain `{root}` |

Glob semantics: `fnmatch` on the repository-relative POSIX path, where `**` matches across
directories (`tests/**` matches `tests/a/b.py`).

Two partitions of a tree's paths, used for different things:

- **Test side / rest**: paths matching `tests`, and every other path. Every replay variant below
  swaps one side between records; nothing on the rest side is assumed harmless, so code written in
  a template, a schema or fixture data outside `tests` counts as code.
- **Test / source / other**: for the hook's message, for naming a verdict (`born-with-code` when
  the call changed source paths) and for the no-sources run. Documentation and `tasks.md` are
  other.

## Record (a commit in the ledger)

| Field | Where | Rule |
|---|---|---|
| tree | the commit's tree | the worktree's tracked and untracked-but-not-ignored files after the call |
| previous | the commit's single parent | absent only for the first record of a worktree |
| `time` | message JSON | ISO 8601 UTC, when the hook ran |
| `session` | message JSON | `session_id` from the hook input |
| `agent` | message JSON | `agent_id` from the hook input, `null` for the main conversation |
| `tool` | message JSON | `tool_name`; `Stop` or `audit` for a snapshot taken by the audit |
| `call` | message JSON | `tool_use_id`, `null` for an audit snapshot |
| `branch` | message JSON | the short name of the branch HEAD points at, `null` when detached |
| `head` | message JSON | the commit HEAD resolved to |

Invariants: a record's tree differs from its parent's (FR-002); records are only ever appended.

## Ledger

The chain reachable from `refs/worktree/test-first/ledger` in one worktree, oldest first when read.
Its oldest record is the **origin**: nothing is born there, because the state before it was not
observed.

## Effective history (derived)

The records that belong to branch *B*'s line of work, oldest first. Walk from the newest record
whose `branch` is *B* towards the origin with a current lineage *L* = *B*:

- a record whose `branch` is *L* is included;
- a record whose `branch` is not *L*, with an older record whose `branch` is *L*, is skipped (a
  visit to another branch, or a detached HEAD during a rebase, and back);
- a record whose `branch` is not *L*, with no older record on *L*, is included and *L* becomes its
  `branch` (the branch *B* was created or renamed from).

Each included record's **previous** is the next older included record; the origin has none. The
change of a record is computed against its previous, so returning to *B* after a visit compares
with *B*'s last state, and `git checkout -b` compares with the state it was created from.

An **imported** test is one that first appears at a record whose `head` differs from its
previous's and whose `head` commit already contains it: it arrived with commits this ledger did not
see being written (a merge, a fast-forward, a pull, a cherry-pick). It is `unobserved`. Tests the
agent wrote and then committed are never imported, because they appeared in an earlier record,
before the commit.

## Base

`git merge-base HEAD <default>`, where `<default>` is the first that exists of: the remote-tracking
branch `origin/HEAD` names, `origin/main`, `origin/master`; and only when there is no `origin`
remote, the local branch named by `init.defaultBranch`, `main`, `master`. Remote-tracking first, so
a local merge into the default branch cannot move the base. The audit refuses when none resolves or
HEAD is on the default branch itself; no network is used to resolve it.

## Run (one replay)

The configured command run on one test file in the scratch worktree set to a given tree, writing
JUnit XML. Outcomes per `testcase`, `id` = `classname` + "::" + `name`: **failed** (a `failure` or
`error` child), **skipped** (a `skipped` child), **passed** (none). A run that writes JUnit with no
test case is conclusive: the file has no tests. That is also what pytest 9.1.1 and Vitest 5.0.3
write for a file that does not exist at the record (measured 2026-10-07), so a deleted file needs
no special case.

A run is **inconclusive** — the file did not load, so the run says nothing about which tests exist
— when it writes no JUnit, or when every case it reports failed and the same command, run on the
same tree with that file's content replaced by bytes no language parses (the **load probe**),
reports exactly the same case ids. The probe runs only for runs whose cases all failed.

Trees a run may use:

| Variant | Tree |
|---|---|
| own | the record's tree |
| before-version of *g* | test side from *g*'s previous, rest from *g* |
| base overlay of *r* | test side from *r*, rest from the base |
| no-sources of *r* | *r*'s tree with every source path removed |

Memo: a run's outcomes are stored under the key (tree id, file, hash of `run`) in the worktree's git
directory (`git rev-parse --git-path test-first/runs`) and reused whenever the same key is needed. A
run stopped by its deadline is stored with that deadline, and is retried only under a longer one. A
run that wrote no JUnit is not stored: it may be the environment's fault (a broken or half-synced
installation), not the tree's. The key does not include the environment; a run recorded under a
different environment is reused, which is the stated assumption that replays use the environment
at audit time. Deleting the memo changes nothing but the time the next audit takes.

## Finding a test's birth

Walk back over the records of the effective history whose change touched the test's file, newest
first. At each such record *t* whose run reports the test, run *t*'s previous:

- conclusive and without the test: the **birth** is *t* (the edit of the file created it, or brought
  it back);
- reports the test: keep walking back;
- inconclusive: run the records before it, one by one, until a conclusive run, and decide as above;
  when that run reports the test, the walk resumes from that record.

A touching record whose own run is inconclusive (a typo that broke the file for a call) is skipped:
it says nothing about the test, so it neither reports nor lacks it.

When the walk reaches a touching record *t₀* whose run does not report the test, the test appeared
between *t₀* and the next touching record without its file changing — its file started to load, or
its id is generated from code or data: scan forward from *t₀* to the first record whose conclusive
run reports it; that is the birth. A test reported at every run back to the origin has no birth;
one whose birth is imported (above) is `unobserved`. The common case — a test written in a file —
costs one run beyond the touching records', and a scan happens only for a test that appeared
without its file changing.

**Restored**: a test born at a record where its file's content is identical to the file's content
at an earlier record of the effective history, at which the test had an accepted verdict (found by
the same procedure, with that earlier record as the newest), keeps that verdict. A `git stash` and
`git stash pop`, or undoing a rename, brings back what was already judged; the redo sequence is not
affected, since the verdict it replaces was not accepted. Limit: the code beside the restored test
is not compared, so an accepted test deleted with its code and written back identically next to
different code keeps its verdict; the test was observed red once, and the mutation check measures
it against the code it now covers.

## Test lifecycle (one test, forward from its birth)

From the birth, the test's file runs at every record of the effective history until the lifecycle
ends — usually one or two
records:

| State | Leaves when |
|---|---|
| waiting to run (skipped) | a run gives failed (→ red pending) or passed (→ judged at first run, at that record *r₁*) |
| red pending | a run gives passed at record *g*: the **green check** |

**Green check** at *g*: run the before-version of *g*. If the test passes there, the code at *g*
satisfies the test as it stood before *g*: verdict `red`. If it fails, the test side changed in the
call that made it pass: `rewritten-to-green`. If the run is inconclusive — the old test side does
not load against the new code, as when one call changes an API together with a shared fixture —
the order cannot be told: `not-judged`, with that reason; the remedy is to change the shared test
support in its own call before the code.

**Judged at first run** at *r₁*:

1. The no-sources run of *r₁* passes: the test's outcome does not depend on any path in `sources`.
   Either the run command reaches code outside the scratch worktree (fix the command), or the test
   exercises code outside `sources` (add its paths to `sources`): `born-green`, with that reason.
2. The base overlay of *r₁* passes: `predates`.
3. *r₁*'s change is not mixed, tests of the feature with accepted verdicts disappeared at *r₁* —
   from any test file *r₁* changed, or, when *r₁* changed no test-side path, from this test's file —
   and the tests whose first run passed at *r₁* are no more than those that disappeared:
   `refactored`, listing them. A mixed call is never a refactor of tests: rewriting an accepted
   test together with the code for a new case is the defect this feature exists for.
   When more passing tests appear than disappear, none of them is refactored: a rename is split from
   a new test.
4. Otherwise `born-with-code` if *r₁*'s change has source paths, else `born-green`.

A disappeared test's verdict is found by the same procedure, taking the record before it
disappeared as its newest.

## Verdict (for each new test)

New test = reported at the newest record by a run of a test file that differs from the base, and
not reported by the base's run of the same file. When that newest run is inconclusive, the file's
tests are taken from its last conclusive run and are `not-judged`, with the reason that the file
does not load at the newest record. A test added to an unchanged test file by a change elsewhere
(a row in a case table outside the file) is not found: a stated limit (FR-022).

| Verdict | Condition | Fails the audit | Final before the end |
|---|---|---|---|
| `red` | first run failed, and the green check passed | no | yes |
| `predates` | judged at first run, step 2 | no | yes |
| `refactored` | judged at first run, step 3 | no | yes |
| `born-with-code` | judged at first run, step 4, source in the change | yes | yes |
| `born-green` | judged at first run, step 1 or 4 | yes | yes |
| `rewritten-to-green` | first run failed, and the green check failed | yes | yes |
| `still-red` | red pending at the newest record | yes | no |
| `unobserved` | no birth in the effective history, or imported | yes | no |
| `not-judged` | a run it depends on exceeded its deadline, the green check was inconclusive, or its file does not load at the newest record | yes | no |
| `never-run` | waiting to run at the newest record (skipped, xfail) | no — listed | no |

A test that has never run vouches for no code, so `never-run` does not fail the audit; it is listed
for the reviewer, and the mutation check sees the code it does not cover.

The Stop hook blocks only on failing verdicts that are final before the end; the story-close audit
fails on every failing verdict. A `not-judged` test's remedy is in its reason: a longer deadline, the
redo sequence after changing shared test support in a call of its own, or making its file load.
A test written and committed in the same call is imported, since its record's HEAD already holds
it: commits go in a call of their own. The remedy for `born-with-code`, `born-green` (step 4) and
`rewritten-to-green` is the redo sequence: remove the test — its file, when it is the file's only
test — revert the code it covers, write the test again in a call that changes nothing else, run it
and see it fail, restore the code. `born-green` from step 1 is fixed in the configuration, as its
reason says.
