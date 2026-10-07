# 0001. The audit checks order; strength is the mutation check's

- Status: accepted
- Date: 2026-10-07
- Source: [research R0 and R8](../../specs/001-observed-test-first/research.md#r0-what-the-machine-checks-and-what-it-does-not)

## Context and problem statement

Test-first with an agent has two claims to check: that each new test failed before the code that
makes it pass (order), and that the test tells right behaviour from wrong (strength). The preset's
checks run inside other people's repositories, in any language. Which of the two does a check the
preset ships decide, and who decides the other?

## Considered options

1. The audit checks order only; strength is the story review's, through the project's mutation
   check where it has one and wrong versions written by hand where it does not.
2. The audit also judges strength, by classifying why a test failed (an assertion against a stub
   versus an import error).
3. The preset ships a mutation tool.

## Decision outcome

Option 1. Order is decidable from the worktree's history in any language. Why a test failed is not:
pytest 9.1.1 reports a missing method, an exception in the code, a stub raising
`NotImplementedError` and a wrong signature all as `<failure>` with no type, and a failure by
assertion against a stub still proves no strength. Mutation testing measures strength directly,
and mutation tools are per language, which the project already knows.

Threat model: an agent taking shortcuts, not one forging evidence; the agent can write the ledger's
ref and the hook settings, and the README says so.

## Consequences

- A later feature does not add failure-reason classification to the audit, nor a mutation tool to
  the preset, without reopening this record.
- The README's limits say the audit checks order, not strength; the review brief carries strength.
- Good: one algorithm for every runner. Bad: a test that failed for the wrong reason passes the
  audit; only the review catches it.
