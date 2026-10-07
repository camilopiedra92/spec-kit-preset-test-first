# Implementation Plan: Observed test-first

**Branch**: `observed-test-first` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-observed-test-first/spec.md`

## Summary

Make "every new test was seen failing" a fact the machine observed. A Claude Code `PostToolUse` hook
records the worktree as a git tree after every tool call, in a per-worktree chain of commits (the
ledger), and tells the agent when one call changed tests and sources together. An audit replays
each test that is new since the base at the record where it last appeared, reads per-test outcomes
from JUnit XML, and passes only when every new test failed there or its behaviour predates the
feature. The `speckit-implement` fragment installs the ledger, runs the audit before each story's
review and drops the self-recorded red runs; the `speckit-tasks` fragment adds property cases for
stated invariants. Released as 2.0.0. Decisions and their alternatives: [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.10, standard library only, for the ledger hook and the audit;
bash for the installer, like the existing Stop-gate installer.

**Primary Dependencies**: none at runtime beyond `git`, `python3` and, for the installer, `jq`
(already required by `install-stop-gate.sh`). Development: ruff, mypy, pytest and pytest-timeout
in a uv dev group (no packaging).

**Storage**: git objects and one per-worktree ref, `refs/worktree/test-first/ledger`; the project
configuration in `.specify/test-first.json`.

**Testing**: pytest for the Python units (JUnit parsing, change classification, births, verdicts);
bash suites end to end in scratch repositories: `tests/ledger.sh` (the hook), `tests/install-ledger.sh`
(the installer), `tests/audit.sh` (the audit over ledgers built from replayed tool-call sequences);
`tests/compose.sh` for the fragments.

**Target Platform**: macOS and Linux (CI: ubuntu-latest); Claude Code; Spec Kit ≥ 1.1.0.

**Project Type**: Spec Kit preset: Markdown fragments plus the scripts they run.

**Performance Goals**: a record in under 100 ms per tool call on ~1,000 tracked files (SC-003;
measured 40–50 ms on renta's 860); an audit of 60 new tests in 20 files under 10 minutes (SC-004).

**Constraints**: the hook never blocks or alters a tool call (FR-004); every replay runs under
`run-bounded.sh` (FR-011, constitution IV); the audit reads nothing the agent writes as evidence
(FR-012).

**Scale/Scope**: one feature branch's ledger: hundreds to a few thousand records.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Status |
|---|---|---|
| I. Append, Never Replace | Both fragments still append; the implement fragment names each core rule it overrides, and `tests/compose.sh` keeps grepping core for them | Pass |
| II. Verified Against the Real CLI | `tests/compose.sh` checks the new scripts land where the fragment runs them; CI's pinned and latest legs are unchanged | Pass |
| III. Every Rule Has Its Evidence | The README gains the source of each changed rule (research.md R1–R11), including the renta measurement and the rules removed | Pass |
| IV. Scripts Fail Closed and Bounded | The installer refuses like `install-stop-gate.sh` and leaves the repository unchanged; the hook reports failures instead of hiding them; every replay goes through `run-bounded.sh` | Pass |
| V. Released by Tag | 2.0.0 in `preset.yml`, CHANGELOG, tag; the new dev files (`pyproject.toml`, `uv.lock`) are export-ignored and `tests/compose.sh` checks it | Pass |

Post-design re-check (after Phase 1): unchanged, all pass. The Python toolchain is new to the
repository and lands as its own setup task, as the global rules ask of a missing role.

## Project Structure

### Documentation (this feature)

```text
specs/001-observed-test-first/
├── plan.md              # This file
├── research.md          # Decisions R1–R11 with alternatives
├── data-model.md        # Record, ledger, birth, verdict, configuration
├── quickstart.md        # End-to-end validation
├── contracts/           # Configuration, hook, audit and installer interfaces
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
commands/
├── speckit.implement.md      # fragment, rewritten (FR-015..FR-019)
└── speckit.tasks.md          # fragment, + property cases (FR-020)
scripts/
├── bash/
│   ├── install-stop-gate.sh  # unchanged
│   ├── install-ledger.sh     # new: hook entry + configuration, one commit
│   └── run-bounded.sh        # unchanged, used by the audit
└── python/
    ├── ledger.py             # new: the PostToolUse hook
    └── audit.py              # new: births and verdicts
tests/
├── compose.sh                # + new scripts installed and referenced; + dev files export-ignored
├── stop-gate.sh, run-bounded.sh
├── ledger.sh                 # new
├── install-ledger.sh         # new
├── audit.sh                  # new
└── python/                   # new: pytest units for ledger.py and audit.py
pyproject.toml, uv.lock       # new: dev group only, export-ignored
```

**Structure Decision**: the existing layout, with `scripts/python/` beside `scripts/bash/`, because
the installed preset runs its scripts by their path under `.specify/presets/test-first/scripts/`.

## Complexity Tracking

No constitution violations to justify.
