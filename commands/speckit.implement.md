## Test-first

- Before the first task, run the suite and the static checks the project
  already runs — the lint and type check its CI, its task runner or its
  constitution declare; add none it does not have — and record the result as
  the baseline.
- This replaces "Execute test tasks before their corresponding implementation
  tasks", the "Tests" phase and "Tests before code" above: the order is per
  case, inside each behaviour task.
- One cycle at a time: take the next case from the task's test list, write
  it as a test, make it pass, then refactor. Never write a test ahead of the
  case in progress. A tasks.md from an earlier version of this preset — a
  test task followed by the task that makes it pass — is read as one task
  whose list holds the cases its test task names; mark both checkboxes when
  it closes.
- Run the new test before writing the code it covers, and confirm it fails
  because the behaviour is missing. An import error, a collection error or a
  missing module proves the test was found, not that it exercises anything:
  stub the code under test until the test runs and fails from inside. Record
  the red run in tasks.md as a plain bullet indented under the case, never a
  checkbox (under the task, in a tasks.md from an earlier version): the
  command and the failure line you saw. That is the evidence
  the cycle went red first.
- A new test that passes on its first run has not been watched failing. Break
  the code it pins on purpose, watch the test fail for the expected reason,
  restore the code, and record that failure and that the behaviour already
  existed. If breaking the code does not make it fail, fix the test: it does
  not exercise what it names.
- A case's expected result comes from the specification, through the task's
  test list: never change it, or the test that encodes it, to reach green.
  If you believe an expected result is wrong, stop that case: remove its
  test if you wrote it, so the suite stays green and the Stop gate keeps
  meaning a real failure; mark the case in the list `stopped: possible spec
  gap` with the reason, and list it in the completion report.
- Then write the least code that makes it pass, and run the whole suite.
- With the suite green, refactor what this cycle left — duplication it added,
  in the code or the tests, a special case the behaviour does not need, a
  function now doing two things, and names that no longer say what they mean.
  Structure only, never behaviour; run the whole suite after each step. If
  the cycle left nothing to clean, move on.
- A case found while implementing — an edge case, a failure mode — does not go
  into the test in progress. Add it to the test list of the task whose
  behaviour it belongs to, marked as found during implementation, and take it
  in turn; one that belongs to no task's behaviour becomes a new task at the
  end of the same story's phase, with the next free task ID — IDs added
  mid-run follow creation, not execution order — citing the requirement it
  falls under. If no requirement covers it, it is a gap in the spec: do not
  decide the behaviour; carry on, and list the gap in the completion report.
- A task is marked `[X]` when every case on its list has been taken — a
  recorded red run, or marked stopped — after a run you saw with no test
  failure and no static-check finding beyond the baseline, and with `git
  status --porcelain --ignored` listing none of the files the task created as
  ignored. The list stays in tasks.md: the story review reads it. If anything
  is red when you stop, say so and show the output.

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
  or use a fresh clone, and repeat the check. A Claude session started in the
  copy runs the copy's Stop gate, which would ask it to fix the wrong
  version: remove the gate's entry under `hooks.Stop` in the copy's
  `.claude/settings.json` first. Run every
  wrong version from a clean build state: a cache keyed on timestamps can
  serve the previous version (Python's bytecode is, to the second — delete every `__pycache__`
  in the copy, `find . -name __pycache__ -prune -exec rm -rf {} +`, and run
  with `PYTHONDONTWRITEBYTECODE=1` from then on).
- Put every run of a wrong version through the preset's runner, from the
  copy's root, with a deadline a few times the suite's normal duration:
  `bash .specify/presets/test-first/scripts/bash/run-bounded.sh <seconds>
  <suite command>`, a pipeline as one `bash -c '...'` argument. A wrong
  version can loop or grow without end, and a tool's timeout, a
  `subprocess.run(timeout=...)` or a kill by name stops one process and
  leaves its children running; the runner kills the command's whole process
  group when it ends or its deadline passes. Exit 124 means the deadline
  fired: the wrong version is caught, but report it, because a test that
  hangs where it should fail needs a timeout of its own.
- Read the story's code as its next maintainer would, for what each cycle's
  refactor step should have removed: duplication, a special case the
  behaviour does not need, a name that does not say what it holds, a
  function doing two things. Name the place and the simpler shape. Nothing
  that is a matter of taste, and nothing a formatter or linter the project
  runs already decides.
- Compare each task's tests with its test list: an expected result that
  differs from the list's, or a listed case with no test that is not marked
  stopped, is a finding.
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
Stop hook that runs tests only to notify or log is not one.

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
