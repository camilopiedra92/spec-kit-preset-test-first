## Test-first

- Before the first task, run the suite and the static checks the project
  already runs — the lint and type check its CI, its task runner or its
  constitution declare; add none it does not have — and record the result as
  the baseline.
- One cycle at a time: a test task, the task that makes it pass, then
  refactor. Never write tests ahead of the cycle in progress.
- Run a test task's tests before writing the code they cover, and confirm they
  fail for the expected reason. An import error, a collection error or a missing
  module proves the test was found, not that it exercises anything: stub the
  code under test until the test runs and fails from inside.
- A new test that passes on its first run has not been watched failing. Break
  the code it pins on purpose, watch the test fail for the expected reason,
  restore the code, and note in tasks.md that the behaviour already existed.
  If breaking the code does not make it fail, fix the test: it does not
  exercise what it names.
- Then write the least code that makes it pass, and run the whole suite.
- With the suite green, refactor what this cycle left — duplication it added,
  in the code or the tests, a special case the behaviour does not need, a
  function now doing two things, and names that no longer say what they mean.
  Structure only, never behaviour; run the whole suite after each step. If
  the cycle left nothing to clean, move on.
- A case found while implementing — an edge case, a failure mode — does not go
  into the test in progress. Append a test task and its implementation task to
  the same story's phase, with the next free task IDs — IDs added mid-run
  follow creation, not execution order — citing the requirement the case
  falls under. If no requirement covers it, it is a gap in the spec: do not
  decide the behaviour; carry on, and list the gap in the completion report.
- A test task closes on its watched failure. Any other task is marked `[X]`
  only after a run you saw with no test failure and no static-check finding
  beyond the baseline, and with `git status --porcelain --ignored` listing
  none of the files the task created as ignored. If anything is red when you
  stop, say so and show the output.

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
story, the feature directory, and this brief:

- Judge the code against `spec.md` (only the story under review), `plan.md`,
  the contracts and `.specify/memory/constitution.md`.
- For each behaviour, write a plausible wrong version in a scratch copy and run
  the suite. A wrong version the suite still passes is a test gap. First
  break something obvious in the copy and watch the suite fail. If it still
  passes, the copy is running the original: an environment copied with the
  repo keeps absolute paths to it (uv's editable `.pth`, script shebangs).
  Rebuild the environment inside the copy (`rm -rf .venv && uv sync` for uv)
  or use a fresh clone, and repeat the check. Run every wrong version from a
  clean build state: a cache keyed on timestamps can serve the previous
  version (Python's bytecode is, to the second — delete every `__pycache__`
  in the copy, `find . -name __pycache__ -prune -exec rm -rf {} +`, and run
  with `PYTHONDONTWRITEBYTECODE=1` from then on).
- Read the story's code as its next maintainer would, for what each cycle's
  refactor step should have removed: duplication, a special case the
  behaviour does not need, a name that does not say what it holds, a
  function doing two things. Name the place and the simpler shape. Nothing
  that is a matter of taste, and nothing a formatter or linter the project
  runs already decides.
- Prove every finding with a concrete input, observed against expected, and
  label anything unproven. Do not edit the repository.

Close each test gap with a test watched failing against that wrong version and
passing against the code. Carry out each structural finding as a refactor:
behaviour unchanged, the whole suite run after each step. Report what the
review found and what it did not fix.

## Stop gate

Instructions stop holding once this run ends; a Stop hook does not. When a
run of the whole suite you saw is green and `.claude/hooks/stop-gate.sh` does
not exist, install the gate before going on, from the repository root:

```bash
bash .specify/presets/test-first/scripts/bash/install-stop-gate.sh <test command>
```

- `<test command>` is the one that runs the whole suite, as the plan's
  Technical Context or the constitution names it, given as separate arguments
  (`uv run pytest -q`, not a quoted string). It runs at the end of every
  turn: if the whole suite takes more than a few seconds, give a fast subset
  and say which in the completion report.
- The installer makes a commit of its own holding only the hook and
  `.claude/settings.json`. If it refuses — something staged, an uncommitted
  `settings.json`, `.claude/` ignored — do not work around it: carry on, try
  again at the next green suite, and if it never installed, put its last
  refusal in the completion report.
- A project with no suite yet gets the gate at the first task that closes
  green.
