# 0002. Runner-agnostic through JUnit XML, one file per run

- Status: accepted
- Date: 2026-10-07
- Source: [research R6 and L7](../../specs/001-observed-test-first/research.md#r6-test-identity-and-outcomes-from-junit-xml-one-file-per-run)

## Context and problem statement

The audit needs, for one test file at one recorded tree, which tests exist and whether each passed,
failed or was skipped — for any project's runner — and must tell a file that does not load from a
file whose tests fail.

## Considered options

1. The project's own command runs one file and writes JUnit XML; load failures are measured at each
   run by running the same command on the same tree with the file made unparseable (the load
   probe).
2. Parse test sources for test names (a parser per language).
3. A table of known runners and how each reports a load failure.
4. Run the whole suite once per record.

## Decision outcome

Option 1. JUnit XML is the one format pytest, Jest (jest-junit), Vitest and PHPUnit all write for a
single file (pytest's and Vitest's measured). One file per run, because a collection error in one
file stops pytest from running the others. Runners disagree on a load failure's shape — pytest
9.1.1 gives one `<error>` case named after the module; Vitest 5.0.3 one `<failure>` named after the
file, also for a file without tests — so the shape is measured when it matters instead of encoded,
which also survives a runner upgrade.

## Consequences

- No per-runner code in the preset; a new runner needs only a `run` command.
- Runners that cannot run one file (Go, whose unit is the package) or write no JUnit are not
  supported, and the README says so.
- Every run whose cases all failed costs a second run (the probe).
- The redo sequence removes a test's file when it is the file's only test, because Vitest reports
  an empty file like one that does not load.
