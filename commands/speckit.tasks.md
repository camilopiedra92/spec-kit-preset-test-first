## Test-first

This section replaces the "Tests are OPTIONAL" rule above, and with it every
rule that applies "if tests requested": tests are required whether or not the
specification or the user asked for them, because an implementation nobody
has watched a test reject is not evidence of anything.

- Two kinds of task. A behaviour task adds or changes behaviour with logic of
  its own — a branch, a computation, a parse, a state change — and carries a
  test list. Setup, configuration, wiring, and code with no logic of its own
  — getters, wrappers, one-line delegations — are plain tasks with none.
- Every behaviour task cites the requirement IDs it implements (`FR-###`,
  `SC-###`), so whoever executes it can trace it without rereading the spec;
  a plain task cites what it serves, if anything.
- A behaviour task's test list holds the cases that pin it, taken from the
  specification and its contracts: one case per line, a concrete input and
  the expected result, ordered from the simplest to the hardest so each
  drives a single small step. Write the cases as plain bullets indented under
  the task's checklist line, never as checkboxes, so the task format above
  still reads one task per line. Implementation turns them into tests one at
  a time and adds the cases it discovers; the list is where it starts, not a
  plan of every cycle.
- No test task separate from the behaviour it pins: this replaces "Each
  interface contract → contract test task [P] before implementation" and
  "Tests specific to that story" above. A contract's cases go in the list of
  the task that implements it. Do not predict how a test will fail before the
  code exists: what a failing run looks like is observed during
  implementation, not planned here.
- The suite fails instead of hanging: every test runs under a time limit,
  so code that loops fails its test rather than holding the run, the Stop
  gate and CI. A framework's own default counts (Jest's and Vitest's 5
  seconds); where there is none (pytest, unittest), the setup phase gets a
  task that sets one: a plugin such as pytest-timeout, which is a new
  dependency and needs the user's approval like any other, or code the
  project writes, and then the task carries a test list. A test that starts
  a process passes it a timeout too.
- A task too big for one short list — a whole module, several requirements
  with nothing in common — is several behaviours; split it.
- A story's tasks are sequential and none is `[P]`. This replaces the
  "Tests (if requested) → Models → …" order above and the tasks template's
  "Tests for User Story N" block ("Write these tests FIRST", every test
  `[P]`): writing all of a story's tests before any of its code is the batch
  the per-case cycle in implementation avoids. Order a story's tasks from the
  simplest behaviour to the hardest, so the first one can be built without
  the others.
