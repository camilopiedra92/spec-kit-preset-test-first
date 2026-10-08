# 0003. A gate blocks a turn once, and lets the next stop through

- Status: accepted
- Date: 2026-10-07 (the Stop gate's rule since 1.4.0, recorded here for the first time)
- Source: [research R12](../../specs/001-observed-test-first/research.md#r12-one-audit-two-entry-points-over-the-branchs-own-history)

## Context and problem statement

The preset's Stop hooks — the 1.x gate on a red suite, the 2.0 audit of test order — run at the end
of every Claude Code turn. When the check fails, should the hook keep the turn from ending until it
passes, or show the failure once and let the next stop end the turn?

## Considered options

1. Block the first stop of a turn with the failure and its remedy; let a stop with
   `stop_hook_active` through.
2. Block every stop until the check passes.
3. Block every stop, with an exception list for failures that cannot be fixed.

## Decision outcome

Option 1. A gate with no way out is the pressure under which agents edit tests to pass:
ImpossibleBench (arXiv 2510.20270) found a way out cut cheating from 54% to 9% for GPT-5. Every
failing verdict has a remedy that always works (the redo sequence, or the configuration), so no
exception list is needed; the one remedy outside the branch — a test file that does not load on
the default branch — is reported, not looped on. The guarantee is that a turn with a final failing
verdict the Stop audit reached ends with the agent shown it once, unless another Stop hook already
blocked that turn; births its budget did not reach wait for a later turn. The full report is the
story-close audit's, which the implement skill runs.

## Consequences

- A later gate the preset adds follows the same rule, or reopens this record.
- The README's limits say a Stop hook does not prevent a turn from ending.
- Both hooks run in parallel at a stop; once either has blocked, the rest of that turn's stops skip
  the audit, so a test born after that block is shown at the next turn or the story close.
