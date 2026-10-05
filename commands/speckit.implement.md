## Test-first

- Run a test task's tests before writing the code they cover, and confirm they
  fail for the expected reason. An import error, a collection error or a missing
  module proves the test was found, not that it exercises anything: stub the
  code under test until the test runs and fails from inside.
- Then write the least code that makes it pass, and run the whole suite.
- Mark a task `[X]` only after a run you saw pass. If the suite is red when you
  stop, say so and show the output.

## Independent review

Before reporting this run complete, hand its work to a reviewer with a fresh
context: a subagent or a separate session, never this conversation or a fork of
it, because a review from the context that wrote the code finds the typos and
none of the assumptions. Give it the commit range this run produced, the feature
directory, and this brief:

- Judge the code against `spec.md` (only the stories this run implemented),
  `plan.md`, the contracts and `.specify/memory/constitution.md`.
- For each behaviour, write a plausible wrong version in a scratch copy and run
  the suite. A wrong version the suite still passes is a test gap.
- Prove every finding with a concrete input, observed against expected, and
  label anything unproven. Do not edit the repository.

Close each test gap with a test watched failing against that wrong version and
passing against the code. Report what the review found and what it did not fix.
