## Test-first

This section replaces the "Tests are OPTIONAL" rule above. Test tasks are
required whether or not the specification or the user asked for them, because
an implementation nobody has watched a test reject is not evidence of anything.

- Every task that adds or changes behaviour with logic of its own — a branch,
  a computation, a parse, a state change — is immediately preceded by a test
  task for that behaviour. Setup, configuration, wiring, and code with no
  logic of its own — getters, wrappers, one-line delegations — need none.
- A test task names the behaviour it pins and the failure expected while the
  implementation does not exist yet.
- One behaviour per task. A task that implements a whole module is a batch of
  red-green cycles; split it.
- A story is a sequence of cycles, each a test task followed by the task that
  makes it pass, and neither is `[P]`. This replaces the "Tests (if requested)
  → Models → …" order above and the tasks template's "Tests for User Story N"
  block ("Write these tests FIRST", every test `[P]`): writing all of a
  story's tests before any of its code is the batch this splits.
- A story's test tasks are its test list: order the cycles from the simplest
  case to the hardest, so each one drives a single small step.
- Every implementation task cites the requirement IDs it implements (`FR-###`,
  `SC-###`), so whoever executes it can trace it without rereading the spec.
