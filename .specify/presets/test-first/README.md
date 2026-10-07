# spec-kit-preset-test-first

A [Spec Kit](https://github.com/github/spec-kit) preset that makes test-first
the default instead of an opt-in. It appends to two core skills and replaces
nothing, so upstream changes to the rest of each skill keep arriving, and it
ships one script: the installer for a Claude Code Stop hook that gates every
turn on the test suite.

| Skill | What the preset adds |
|---|---|
| `speckit-tasks` | Tests are required (overriding core's "Tests are OPTIONAL") for behaviour with logic of its own; one task per behaviour, carrying its test list — concrete cases, input and expected result, taken from the spec before any code exists, simplest first; no separate test tasks and no predicted failures; never `[P]`; tasks cite their `FR-`/`SC-` IDs; every test runs under a time limit, set by a setup task where the framework has none |
| `speckit-implement` | A test counts once it has failed from inside, not on an import or collection error, and one that passes on its first run is investigated; the suite's per-test time limit is confirmed before the first task; one red-green-refactor cycle per case of the task's list, each red run recorded under the case; a case's expected result is never changed to reach green — one believed wrong is stopped and reported as a spec gap; a case found mid-implementation joins the list instead of growing the current test; a task is marked done only on a green suite and no lint or type finding beyond a baseline taken before the first task; ignore files and tool config are touched only as far as the feature needs; each completed user story gets a review from a fresh context that tries wrong versions of the code against the tests, each run under a deadline that kills its process group, and reads the code for what the refactor step should have removed; every test gap is closed with a test and every structural finding with a refactor; the first green suite installs the Stop gate (below) |

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
Stop entry for it already there, a missing `run-bounded.sh`, or a commit hook
that rejects its commit. To
change the command later, edit `TEST_COMMAND` in the hook. To turn the gate
off, remove its entry under `hooks.Stop` in `.claude/settings.json` and keep
the hook file: the file is what `/speckit-implement` looks for, so the gate
stays off. Removing the file as well, as reverting the feature that installed
it does, means the next run installs it again. Only with `.specify/` at the
repository root, and not where the project has a gate of its own: a Stop
hook whose command or script runs the suite, or a fast subset, and exits 2
when it is red. A hook that runs tests only to notify or log does not count.
The installer needs `jq`; the hook does not.

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
specify preset add --from https://github.com/camilopiedra92/spec-kit-preset-test-first/archive/refs/tags/v1.6.0.zip
```

To move a project to a newer release:
`specify preset update test-first --from <that tag's zip URL>`.

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
and that nothing survives. CI runs all three against the pinned Spec Kit
release on every push and against the latest release weekly.

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

Why this shape, by source (searched 2026-10-05):

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

