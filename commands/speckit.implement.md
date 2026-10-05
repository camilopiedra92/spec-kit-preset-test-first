## Test-first

- Run a test task's tests before writing the code they cover, and confirm they
  fail for the expected reason. An import error, a collection error or a missing
  module proves the test was found, not that it exercises anything: stub the
  code under test until the test runs and fails from inside.
- Then write the least code that makes it pass, and run the whole suite.
- Mark a task `[X]` only after a run you saw pass. If the suite is red when you
  stop, say so and show the output.
