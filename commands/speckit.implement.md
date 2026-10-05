## Test-first

- Run a test task's tests before writing the code they cover, and confirm they
  fail for the expected reason. An import error, a collection error or a missing
  module proves the test was found, not that it exercises anything: stub the
  code under test until the test runs and fails from inside.
- A new test that passes on its first run has not been watched failing. Find
  out why before going on: either the behaviour already exists — say so in
  tasks.md and do not count it as test-first — or the test does not exercise
  what it names, and it is fixed until it fails against the missing code.
- Then write the least code that makes it pass, and run the whole suite.
- With the suite green, refactor: remove the duplication the least code left,
  in the code and in the tests, and make names say what they mean. Change
  structure, never behaviour, and run the whole suite after each step.
  Behaviour the refactor seems to need is a new test first.
- A case found while implementing — an edge case, a failure mode — does not go
  into the test in progress. Add it to tasks.md as a new test task in the same
  story, citing the requirement it falls under. If no requirement covers it,
  that is a gap in the spec: report it rather than decide the behaviour.
- Mark a task `[X]` only after a run you saw pass: the whole suite, and the
  static checks the project already runs — the lint and type check its CI, its
  task runner or its constitution declare. Add no check it does not have. If
  anything is red when you stop, say so and show the output.

## Project setup

This narrows "Project Setup Verification" above. A project's ignore files and
tool configuration belong to the project, not to this run:

- `.gitignore`: append patterns only for files this feature's build or tests
  generate, and none that matches a tracked file — after the change,
  `git ls-files -ci --exclude-standard` must list nothing new.
- Every other ignore file, and linter or formatter configuration
  (`eslint.config.*`, `.eslintrc*`, `.prettierrc*`): create or edit it only
  when plan.md introduces that tool. Otherwise list the patterns you would
  have added in the report.

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
  the suite. A wrong version the suite still passes is a test gap.
- Prove every finding with a concrete input, observed against expected, and
  label anything unproven. Do not edit the repository.

Close each test gap with a test watched failing against that wrong version and
passing against the code. Report what the review found and what it did not fix.
