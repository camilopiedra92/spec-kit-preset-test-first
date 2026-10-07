# Implementation Plan: Observed test-first

**Branch**: `observed-test-first` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-observed-test-first/spec.md`

## Summary

Make "every new test was seen not passing before the code that makes it pass" a fact the machine
observed. A Claude Code `PostToolUse` hook records the worktree as a git tree after every tool call,
in a per-worktree chain of commits (the ledger), and tells the agent when one call changed tests and
sources together. An audit searches the branch's own line of records, replays each new test's
file where the test was born and where it first passed — swapping the whole test side or the whole
rest of the tree between records — reads per-test outcomes from JUnit XML, and
passes only when every new test was red there and its earlier version passes after the call that
made it pass — or its behaviour predates the feature, or it replaced accepted tests. Replays are
memoized by tree, so the same audit runs as a Stop hook every turn, within a budget, and in full at
each story's close. It checks order; strength stays with the mutation check at the story review.
The `speckit-implement` fragment installs the ledger, runs the full audit before each story's
review and drops the self-recorded red runs; the `speckit-tasks` fragment adds property cases for
stated invariants. Released as 2.0.0. Decisions and their alternatives: [research.md](research.md).

## Technical Context

**Language/Version**: Python ≥ 3.10, standard library only, for the ledger hook and the audit;
bash for the installer, like the existing Stop-gate installer.

**Primary Dependencies**: none at runtime beyond `git`, `python3` and, for the installer, `jq`
(already required by `install-stop-gate.sh`). Development: ruff, mypy, pytest and pytest-timeout
in a uv dev group (no packaging).

**Storage**: git objects and one per-worktree ref, `refs/worktree/test-first/ledger`; the replay
memo under the worktree's git directory (`git rev-parse --git-path test-first/runs`); the project
configuration in `.specify/test-first.json`.

**Testing**: pytest for the Python units (JUnit parsing, change classification, effective history,
births, the green check, verdicts, the memo);
bash suites end to end in scratch repositories: `tests/ledger.sh` (the hook), `tests/install-ledger.sh`
(the installer), `tests/audit.sh` (the audit and its Stop entry over ledgers built from replayed
tool-call sequences);
`tests/compose.sh` for the fragments. The audit's units build ledgers from recorded call
sequences, so every verdict and every branch move of data-model.md has a case.

**Target Platform**: macOS and Linux (CI: ubuntu-latest); Claude Code; Spec Kit ≥ 1.1.0.

**Project Type**: Spec Kit preset: Markdown fragments plus the scripts they run.

**Performance Goals**: a record in under 100 ms per tool call on ~1,000 tracked files (SC-003;
measured 30–50 ms on renta's 860–861); a story-close audit of 60 new tests in 20 files under 2
minutes with a warm memo and under 15 from an empty one (estimated, to be measured), and a Stop
audit of one turn's test and code under 30 seconds, for pytest (SC-004).

**Constraints**: the hook never blocks or alters a tool call (FR-004); every replay runs under
`run-bounded.sh` (FR-011, constitution IV); the Stop audit starts no run after its budget and blocks
once per turn (FR-024); the audit reads nothing the agent writes as evidence (FR-012).

**Scale/Scope**: one feature branch's ledger: hundreds to a few thousand records.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Status |
|---|---|---|
| I. Append, Never Replace | Both fragments still append; the implement fragment names each core rule it overrides, and `tests/compose.sh` keeps grepping core for them | Pass |
| II. Verified Against the Real CLI | `tests/compose.sh` checks the new scripts land where the fragment runs them; CI's pinned and latest legs are unchanged | Pass |
| III. Every Rule Has Its Evidence | The README gains the source of each changed rule (research.md R0–R14), including the renta measurement, the runner measurements and the rules removed | Pass |
| IV. Scripts Fail Closed and Bounded | The installer refuses like `install-stop-gate.sh` and leaves the repository unchanged; the hook reports failures instead of hiding them; every replay goes through `run-bounded.sh`; the Stop audit has a budget, and a birth it did not judge is never a pass; a pass against other code is accepted only after the no-sources run fails (FR-025) | Pass |
| V. Released by Tag | 2.0.0 in `preset.yml`, CHANGELOG, tag; the new dev files (`pyproject.toml`, `uv.lock`) are export-ignored and `tests/compose.sh` checks it | Pass |

| VI. Observed, Not Reported (added by this feature, below) | The audit reads git objects, the ledger and runner reports only (FR-012); the README states what it does not check (FR-022) | Pass |

Post-design re-check (after Phase 1, and again after the revisions of 2026-10-07): all pass, with
the constitution amended as below.

## Constitution amendment (1.0.0 → 1.1.0)

This feature's decisions bind every later change in places the constitution did not cover, so the
amendment was made inside the feature, before `/speckit-tasks`, in a commit of its own whose
message carries the impact report (Governance): `/speckit-analyze` checks the plan against the
constitution, and would otherwise check it against the principles this feature changes. Each change is judged against its sources, not
kept because the text already says it:

- **New principle VI. Observed, Not Reported** — a check the preset ships judges what tools
  observed (the repository's states as git records them, a runner's report) and never a file the
  agent writes as evidence of its own work; and it states, where the user reads it, what it does
  not check. Rationale: the agent's self-report is the defect L1 measured, and every framework in
  research L3 that "verifies" test-first verifies the agent's own report. Check: the audit's tests
  build their inputs from recorded states and runner output only; a reviewer looks for a read of
  `tasks.md` or any agent-written evidence in `scripts/`, and for the README's limits section.
- **IV. Scripts Fail Closed and Bounded**, expanded — a script writes only inside the repository's
  git directories (per-worktree and common: `git worktree add` registers there), a temporary
  directory it removes, and the one commit an installer makes; it leaves nothing registered when
  killed, pruning what an earlier run left; and it opens no network connection of its own. What a
  command the project configures writes or fetches (a `uv run` syncing `.venv`, a cache) is the
  project's. The ledger now stores worktree states, which must not leave the machine by the
  preset's doing (research R2). Its Check names the new suites: `tests/ledger.sh`,
  `tests/install-ledger.sh`, `tests/audit.sh` and the pytest units.
- **III. Every Rule Has Its Evidence**, widened — a measured run is dated with the versions of the
  tools it ran on (Spec Kit, Claude Code, git, the test runner), not only Spec Kit's: the audit's
  rules rest on pytest's and Vitest's reports and on git's ref behaviour (research L7).
- **V. Released by Tag**, Check widened — `tests/compose.sh` also fails if the archive carries
  `pyproject.toml`, `uv.lock` or `docs/`; all three are added to `.gitattributes` as
  export-ignore (`tests/`, the Python units included, already is).

Version: MINOR (a principle added, two materially expanded), 1.0.0 → 1.1.0. Not changed: I and II,
which the design meets as written. Considered and not made a principle: "runner-agnostic through
JUnit" and "gates block once per turn" — they bind later features but are design choices with
alternatives, so they go to decision records (below), where their alternatives are kept.

## Decisions that outlive the feature

Before the pull request opens, the decisions a later feature would otherwise reopen move out of
`research.md` into `docs/decisions/` in MADR's shape (context, options, outcome, consequences),
each linking its research entry, and `CLAUDE.md` points there:

- `0001-order-not-strength.md` — the audit checks order; strength is the mutation check's; the
  threat model is an agent taking shortcuts (R0).
- `0002-runner-agnostic-through-junit.md` — one test file per run, JUnit XML, load failures
  measured by probe at each run, no per-runner code; runners that cannot run one file are not
  supported (R6).
- `0003-gates-block-once-per-turn.md` — a Stop hook shows a failing check once per turn and lets
  the next stop through, with a remedy that always works instead of an exception list (R12; the
  1.x Stop gate's reason, recorded here for the first time).

`CLAUDE.md` gains the new commands (`uv run ruff check`, `uv run mypy`, `uv run pytest`,
`tests/ledger.sh`, `tests/install-ledger.sh`, `tests/audit.sh`) and `scripts/python/` and
`docs/decisions/` in "Where things live", in the commits that make them true.

CI: the Python checks and the new suites run as steps of the existing `compose` job, so the check
the ruleset already requires (`compose (pinned)`) covers them and `~/dotfiles/github/repos.json`
needs no change; a separate job would be a check the ruleset does not require. The Python toolchain is new to the
repository and lands as its own setup task, as the global rules ask of a missing role.

## Project Structure

### Documentation (this feature)

```text
specs/001-observed-test-first/
├── plan.md              # This file
├── research.md          # Decisions R0–R14 with alternatives; landscape L1–L9
├── data-model.md        # Record, ledger, effective history, runs, lifecycle, verdicts
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
│   ├── install-ledger.sh     # new: both hook entries + configuration, one commit
│   └── run-bounded.sh        # unchanged, used by the audit
└── python/
    ├── ledger.py             # new: the PostToolUse hook and the snapshot both entry points share
    └── audit.py              # new: the birth search, the replays and their memo; the Stop entry point
tests/
├── compose.sh                # + new scripts installed and referenced; + dev files export-ignored
├── stop-gate.sh, run-bounded.sh
├── ledger.sh                 # new
├── install-ledger.sh         # new
├── audit.sh                  # new
└── python/                   # new: pytest units for ledger.py and audit.py
pyproject.toml, uv.lock       # new: dev group only, export-ignored
docs/decisions/               # new: 0001–0003, export-ignored
.specify/memory/constitution.md   # amended to 1.1.0 (above)
CLAUDE.md                     # commands and paths of this feature
```

**Structure Decision**: the existing layout, with `scripts/python/` beside `scripts/bash/`, because
the installed preset runs its scripts by their path under `.specify/presets/test-first/scripts/`.

## Complexity Tracking

No constitution violations to justify.
