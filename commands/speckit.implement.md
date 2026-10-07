## Test-first

- Before the first task, run the suite and the static checks the project
  already runs — the lint and type check its CI, its task runner or its
  constitution declare; add none it does not have — and record the result as
  the baseline.
- Before the first task, also confirm every test runs under a time limit:
  the framework's default, or one a setup task set. If there is none and no
  task sets one, add that task at the start of the setup phase, with the
  next free task ID and, when the limit is code the project writes, a test
  list, and take it first: code that loops would otherwise hang
  the suite, the Stop gate and CI instead of failing a test. A per-test
  limit cannot stop a synchronous loop in JavaScript, which never yields to
  the timer; the Stop gate's deadline and the review's runner bound that.
- This replaces "Execute test tasks before their corresponding implementation
  tasks", the "Tests" phase and "Tests before code" above: the order is per
  case, inside each behaviour task, and the machine observes it.

## Ledger

Whether each test failed before its code is not something this run reports:
a hook records the worktree after every tool call, and an audit replays the
records. Before the first task, where `.specify/` sits at the root of the git
repository and `.specify/test-first.json` does not exist, install it from
that root, on the feature's branch:

```bash
python3 .specify/presets/test-first/scripts/python/cli.py install \
  --tests '<glob>'... --sources '<glob>'... --run '<command>'
```

- `--tests`: every path on the test side — test files and their helpers,
  fixtures and shared configuration (`conftest.py`, `tests/**`, `**/*.test.ts`).
  `--sources`: the project's code. Globs are git's (`**/` matches no directory
  or any). Take both from the plan's project structure.
- `--run`: a command that runs the one test file `{file}` and writes JUnit XML
  to `{junit}`. It runs in a scratch worktree holding only the record's
  files, so it reuses the real worktree's environment through `{root}`, and
  must not import the real worktree's code: for pytest in a uv project
  `PYTHONPATH=src UV_PROJECT_ENVIRONMENT={root}/.venv uv run --no-sync python -m pytest -q -p no:cacheprovider --junitxml={junit} {file}`
  (`PYTHONPATH=src` puts the record's package ahead of the editable install);
  for Vitest
  `ln -s {root}/node_modules node_modules && node_modules/.bin/vitest run {file} --reporter=junit --outputFile={junit}`.
  Its exit status is ignored; only the JUnit file is read. A runner that
  cannot run one file (Go) is not supported.
- It makes a commit of its own holding only `.specify/test-first.json` and
  `.claude/settings.json`. If it refuses, or the plan does not say enough to
  write the three flags, do not work around it: carry on without it and put
  the reason in the completion report.

The records hold what each call changed, so the cycle below is made of
calls. A call is one tool use: one write, one edit, one shell command.

## Cycle

- One cycle at a time: take the next case from the task's test list, write
  it as a test, make it pass, then refactor. Never write a test ahead of the
  case in progress. A tasks.md from an earlier version of this preset — a
  test task followed by the task that makes it pass — is read as one task
  whose list holds the cases its test task names; mark both checkboxes when
  it closes. Its recorded red runs stay as they are; new cases get none.
- Write the case's test in a call that changes no source file, and run it.
  It must fail from inside: an import error, a collection error or a missing
  module proves the test was found, not that it exercises anything. Stub the
  code under test, in a call of its own that changes no test, until the test
  runs and fails from inside.
- Then write the least code that makes it pass, in a later call that changes
  no test-side path, and run the whole suite. A test changed in the same call
  as the code that makes it pass is the defect the audit exists to find.
- A new test that passes on its first run either pins behaviour the feature
  already had before this feature, which the audit accepts by itself, or was
  written after its code. Do not break the code to show it can fail. If its
  code was written in this feature, in this session or an earlier one, take
  the redo sequence: remove the test — its file, when it is
  the file's only test — revert the code it covers, write the test again in a
  call that changes nothing else, run it and see it fail, then restore the
  code.
- A case's expected result comes from the specification, through the task's
  test list: never change it, or the test that encodes it, to reach green.
  If you believe an expected result is wrong, stop that case: remove its
  test if you wrote it, so the suite stays green and the Stop gate keeps
  meaning a real failure; mark the case in the list `stopped: possible spec
  gap` with the reason, and list it in the completion report.
- With the suite green, refactor what this cycle left — duplication it added,
  in the code or the tests, a special case the behaviour does not need, a
  function now doing two things, and names that no longer say what they mean.
  Structure only, never behaviour; run the whole suite after each step. A
  test renamed, moved or consolidated (several cases into one parametrized
  test) changes in a call that changes only test-side paths — not tasks.md,
  not a file a run leaves behind. If the cycle left
  nothing to clean, move on.
- Commit in a call of its own: a test written and committed in one call
  reaches the ledger already in HEAD, as if it came from elsewhere.
- A subagent that writes code or tests works in this worktree, one at a time:
  a worktree of its own has a ledger of its own, removed with it, and two
  writers at once land in one record. This narrows "parallel tasks [P] can
  run together" above: tasks marked `[P]` still run one after another.
- A case found while implementing — an edge case, a failure mode — does not go
  into the test in progress. Add it to the test list of the task whose
  behaviour it belongs to, marked as found during implementation, and take it
  in turn; one that belongs to no task's behaviour becomes a new task at the
  end of the same story's phase, with the next free task ID — IDs added
  mid-run follow creation, not execution order — citing the requirement it
  falls under. If no requirement covers it, it is a gap in the spec: do not
  decide the behaviour; carry on, and list the gap in the completion report.
- A task is marked `[X]` when every case on its list has been taken — its
  test written and run as above, or marked stopped — after a run you saw with
  no test failure and no static-check finding beyond the baseline, and with
  `git status --porcelain --ignored` listing none of the files the task
  created as ignored. The list stays in tasks.md: the story review reads it.
  If anything is red when you stop, say so and show the output.

## Story audit

When a user story's last task closes, and before its review, run the audit
from the repository root:

```bash
python3 .specify/presets/test-first/scripts/python/cli.py audit
```

Exit 0 is a pass. Exit 1 lists each new test with its verdict, and each
failing verdict with its remedy: the redo sequence above for a test born
with its code, born green or rewritten to green, or one the ledger never saw
born (`unobserved`); for one born green because it passes without any
source, the configuration, committed on its own; for `still-red`, the code
that makes it pass, in a call that changes no test-side path; for
`not-judged`, what its reason says. Apply them and run it again until it
passes; a remedy outside this branch (a file that does not load on the
default branch) goes in the completion report instead. Exit 2 is a refusal
whose message says why. Give the last report to
the reviewer. Without the ledger installed, say in the completion report
that the story was not audited.

The ledger's Stop hook runs the same audit at the end of every turn, within a
budget, and blocks the turn once when a new test is born with its code, born
green or rewritten to green: apply that test's remedy before going on. It
also blocks once when the audit cannot run (a configuration or git error),
with the error.

## Project setup

This narrows "Project Setup Verification" above. A project's ignore files and
tool configuration belong to the project, not to this run:

- `.gitignore`: append patterns only for files this feature's build or tests
  generate. `git ls-files -ci --exclude-standard` lists the tracked files a
  pattern ignores; it must list nothing after the change that it did not
  before. Files the feature has yet to create are checked as each task
  closes (above).
- Every other ignore file, and linter or formatter configuration
  (`eslint.config.*`, `.eslintrc*`, `.prettierrc*`): create or edit it only
  when the tool is new to the repository in this feature.

## Independent review

When a user story's phase is complete, and before the next phase starts, hand
that story's work to a reviewer with a fresh context: a subagent or a separate
session, never this conversation or a fork of it, because a review from the
context that wrote the code finds the typos and none of the assumptions. Once
per story, not per task: a task is too small to show how its tests fall short
together with its neighbours', and the story is the unit the spec gives an
independent test. Work after the last story (polish) is reviewed the same way
before the run is reported complete. Give the reviewer the commits for that
story, the feature directory, the story audit's last report, and this brief:

- Judge the code against `spec.md` (only the story under review), `plan.md`,
  the contracts and `.specify/memory/constitution.md`. The audit says each
  test failed before its code; it does not say the tests are strong enough
  to catch a wrong version. That is this review's.
- Where the project's constitution names a mutation check, or its CI runs
  one (mutmut, Stryker, PIT, cargo-mutants), run it over the story's changes:
  each surviving mutant is a test gap, unless it is equivalent to the code,
  which you say and justify. Otherwise, for each behaviour, write a plausible
  wrong version in a scratch copy and run the suite. A wrong version the suite still passes is a test gap. First
  break something obvious in the copy and watch the suite fail. If it still
  passes, the copy is running the original: an environment copied with the
  repo keeps absolute paths to it (uv's editable `.pth`, script shebangs).
  Rebuild the environment inside the copy (`rm -rf .venv && uv sync` for uv)
  or use a fresh clone, and repeat the check. A Claude session started in the
  copy runs the copy's hooks — the Stop gate would ask it to fix the wrong
  version: remove the entries under `hooks.Stop` and `hooks.PostToolUse` in
  the copy's `.claude/settings.json` first. Run every
  wrong version from a clean build state: a cache keyed on timestamps can
  serve the previous version (Python's bytecode is, to the second — delete every `__pycache__`
  in the copy, `find . -name __pycache__ -prune -exec rm -rf {} +`, and run
  with `PYTHONDONTWRITEBYTECODE=1` from then on).
- Put every run of a wrong version through the preset's runner, from the
  copy's root: `bash .specify/presets/test-first/scripts/bash/run-bounded.sh
  <seconds> <suite command>`. The deadline is whole seconds, a few times the
  suite's normal duration, and with 5 seconds added for the runner's grace
  period it stays under your shell tool's own timeout, so the status comes
  back to you; a pipeline goes in as one `bash -c '...'`
  argument, and environment variables are exported before the call, not
  written after the seconds. A wrong version can loop or grow without end,
  and a tool's timeout, a `subprocess.run(timeout=...)` or a kill by name
  stops one process and leaves its children running; the runner kills the
  command's whole process group when it ends or its deadline passes. Exit
  124 means the deadline fired: the wrong version is caught, but report it,
  because a test that hangs where it should fail needs a timeout of its own.
  Exit 2 with a usage line, or 127, means the call was wrong, not that the
  suite caught anything.
- Read the story's code as its next maintainer would, for what each cycle's
  refactor step should have removed: duplication, a special case the
  behaviour does not need, a name that does not say what it holds, a
  function doing two things. Name the place and the simpler shape. Nothing
  that is a matter of taste, and nothing a formatter or linter the project
  runs already decides.
- Compare each task's tests with its test list: an expected result that
  differs from the list's, or a listed case with no test that is not marked
  stopped, is a finding. A failing verdict in the audit's report is one too.
- Prove every finding with a concrete input, observed against expected, and
  label anything unproven. Do not edit the repository.

Close each test gap with a test watched failing against that wrong version and
passing against the code. Carry out each structural finding as a refactor:
behaviour unchanged, the whole suite run after each step. Report what the
review found and what it did not fix.

## Stop gate

Instructions stop holding once this run ends; a Stop hook does not. Where
`.specify/` sits at the root of the git repository and the project has no
gate of its own, install the gate the first time a run of the whole suite you
saw is green and `.claude/hooks/stop-gate.sh` does not exist, before going on,
from that root. A gate of its own is a `hooks.Stop` entry in
`.claude/settings.json` whose command — read the script it runs, not only the
entry — runs the suite, or a fast subset of it, and exits 2 when it is red; a
Stop hook that runs tests only to notify or log is not one. It is a second
Stop hook beside the ledger's, and they answer different questions: the gate
whether the suite is green, the ledger's audit whether each new test failed
before its code. Claude Code runs both at every stop.

```bash
bash .specify/presets/test-first/scripts/bash/install-stop-gate.sh <test command>
```

- `<test command>` is the one that runs the whole suite, as the plan's
  Technical Context or the constitution names it, given as separate arguments
  (`uv run pytest -q`, not one quoted string). A command that needs a shell —
  a variable assignment, `&&`, a pipe — goes through one:
  `sh -c 'CI=1 npm test'`. It runs at the end of every turn: if the whole
  suite takes more than a few seconds, give a fast subset and say which in
  the completion report.
- The installer makes a commit of its own holding only the hook and
  `.claude/settings.json`. If it refuses, do not work around it and do not
  retry at every task: try once more after the last task, and if it still
  refuses, put its message in the completion report.
- A project with no suite yet gets the gate at the first green run of the
  suite this run creates, which is its first case's green, not the end of its
  first task.
- With `.specify/` below the repository root, do not install it; say so in
  the completion report.
