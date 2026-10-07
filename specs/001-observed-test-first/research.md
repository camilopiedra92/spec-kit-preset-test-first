# Research: Observed test-first

Decisions for [plan.md](plan.md), each with what was considered and why it lost. Sources were read
or measured on 2026-10-07 unless dated otherwise.

## R1. Observe the worktree's state, not the agent's commands

**Decision**: a Claude Code `PostToolUse` hook on every tool records the worktree's state after each
call.

**Rationale**: what matters is which files a call changed, whatever wrote them. In the renta run
that motivates the feature, the mixed writes came through shell heredocs and `python3 - <<EOF`, not
the file-editing tool. `PostToolUse` fires for every tool, subagents included, and passes
`session_id`, `agent_id` and `cwd` (Claude Code hooks reference).

**Alternatives considered**:
- Parse each Bash command for the files it writes: unsound. spec-gates v0.4.0 spends 1,347 lines on
  it in `validate-bash.sh` and still allows a `python3 - <<'EOF'` that writes source and test (probe
  run 2026-10-07).
- Block writes before they happen (`PreToolUse`), as TDD Guard does: sees the Edit/Write tools'
  arguments only; TDD Guard's own docs warn shell writes bypass it unless shell is denied.
- Judge each action with a language model against the transcript (Probity): a verdict that is
  still a model's, a turn of tokens per action, and the transcript is written asynchronously and
  can lag the current turn (hooks reference).
- Read the session transcript afterwards: it holds commands, not their effects on files.

## R2. The ledger is a chain of commits under a per-worktree ref

**Decision**: each record is `git commit-tree <tree> -p <previous record>` with a JSON message, and
`refs/worktree/test-first/ledger` points at the newest; the tree comes from a temporary index
seeded from the worktree's own index, `git add -A`, `git write-tree`. A call that leaves the tree
unchanged adds no record. The ref moves with `git update-ref <ref> <new> <old>`, retried on a race.

**Rationale**: reachable objects survive `git gc`; `refs/worktree/` is per worktree by git's
definition, so a linked worktree keeps its own ledger; `update-ref` with the old value is atomic;
`git log refs/worktree/test-first/ledger` inspects it. Measured on renta (860 tracked files): 40–50
ms per snapshot.

**Alternatives considered**:
- A JSONL file plus loose tree objects: unreachable objects are pruned by gc after two weeks by
  default (`gc.pruneExpire`), so a long feature would lose its early births.
- `git stash create`: records the index as well as the worktree, and a stash commit's shape is not
  a plain tree to diff.
- One ref per record: thousands of refs slow every ref operation and clutter `git log --all`.

## R3. Python standard library for the hook and the audit

**Decision**: `ledger.py` and `audit.py`, standard library only, run as `python3 <path>`.

**Rationale**: the hook reads JSON on stdin and the audit parses JUnit XML; both are in the
standard library. Spec Kit's scripts already need `python3` once a preset is installed. The preset
install drops the executable bit (specify 1.1.0), so scripts are run through their interpreter.

**Alternatives considered**: bash with `jq` — the Stop-gate hook was written to need no `jq` at run
time, and XML in bash is not credible.

## R4. Telling the agent: exit 2 with stderr

**Decision**: when a call changed test and source files, or a record could not be made, the hook
exits 2 with a message on stderr.

**Rationale**: for `PostToolUse`, exit 2 shows stderr to Claude and cannot block, since the tool has
already run (hooks reference) — FR-004 and FR-005 exactly.

**Alternatives considered**: `hookSpecificOutput.additionalContext` in JSON on stdout — equivalent
reach, more surface; kept as the fallback if exit-2 behaviour changes.

## R5. The audit applies FAIL_TO_PASS at each test's birth

**Decision**: every test new since the base is run at the record where it last appeared; it must
fail there by an assertion (an error is followed to the first non-error outcome). One that passes
there is accepted only if it also passes against the source at the base, with its file as it was
at birth: then its behaviour predates the feature.

**Rationale**: SWE-bench validates a test as encoding new behaviour when it fails before the change
and passes after, and excludes tests that call newly created functions because their "failure" is
an import error (arXiv 2310.06770). Applied at birth, the same check is what "red first" means.
Tests written without the code in view catch more faults (arXiv 2607.05139: 25% vs 14%), and agents
fake self-reported red (Böckeler, martinfowler.com, "TDD in the agent loop"; ImpossibleBench, arXiv
2510.20270). Clarified 2026-10-07: a test born green fails the audit unless it predates the feature.

**Alternatives considered**:
- FAIL_TO_PASS once per pull request against the base: blind to order (code written first still
  fails at base), and most new tests in a feature call new symbols, so they error at base.
- Keep the agent's red record in `tasks.md`: it is the defect observed.
- Accept a test born green from a test-only call: leaves code-first open one call apart.

## R6. Test identity and outcomes from JUnit XML

**Decision**: the project's configured command runs given test files and writes JUnit XML; a test
is `classname` + `name` of a `testcase`; its outcome is failure, error, skipped or pass.

**Rationale**: the one result format pytest, Jest (jest-junit), Vitest, Go (gotestsum) and PHPUnit
all write, so the audit stays language-agnostic.

**Alternatives considered**: parsing test sources (one parser per language); `pytest
--collect-only` (pytest only).

## R7. Replays in one isolated worktree, cleaned and bounded

**Decision**: the audit adds one detached scratch worktree, moves it to each record with `git
read-tree -u --reset <tree>`, runs `git clean -fdx` before every run, and runs the command through
`run-bounded.sh` with a deadline. The command may name `{root}`, the real worktree, to reuse its
installed environment.

**Rationale**: a run must see the record's files and nothing else: in renta a same-size edit within
the same second reused a stale `.pyc` and three false failures followed (tasks.md of feature 001,
T004); `git clean -fdx` removes every untracked cache in any language. A replay of a wrong record can
hang, and constitution IV requires a deadline that kills the process group.

**Alternatives considered**: a fresh clone per record (seconds each, and an environment per clone);
replaying in the real worktree (destroys uncommitted work — the hazard recorded in renta's
memory of mutating a shared tree).

## R8. The story review uses the project's mutation check

**Decision**: where the project's constitution or CI names a mutation check, the reviewer runs it
over the story's changes and treats each survivor as a test gap or a justified exception;
otherwise the reviewer writes wrong versions by hand, as in 1.x.

**Rationale**: mutation testing is the oracle Böckeler recommends for regression quality, and
reporting mutants on the code under review is Google's practice (Petrović & Ivanković, ICSE-SEIP
2018). renta gained such a gate on 2026-10-07 (`scripts/mutation_gate.py`), which ran in under a
minute for one touched method.

**Alternatives considered**: shipping a mutation tool in the preset — tools are per language, and
the project already knows its own.

## R9. Property cases for stated invariants

**Decision**: when the spec states an invariant (conservation, ordering, a bound), the implementing
task's test list includes a property case over generated inputs.

**Rationale**: Kiro derives correctness properties from EARS requirements and runs them as
property-based tests (kiro.dev/docs/specs/correctness, updated 2026-08-04); Anthropic's agentic
property-based testing found valid bugs in 56% of its reports across 100 Python packages, 86% of its
top-ranked ones (arXiv 2510.09907). The cases still go through the audit: a property born green
fails like any test (Kiro's own page warns a weak property passes while behaviour is wrong).

**Alternatives considered**: property cases for every task — no evidence of value where no
invariant is stated, and it inflates lists.

## R10. Rules removed, and what was not adopted

**Removed from `speckit-implement`**: recording the red run under each case, and accepting a test
that passed on its first run by breaking the code on purpose. Evidence: renta feature 001 on 1.6.0,
27 of ~60 cases recorded as first-run passes, 11 test runs from one call writing code and test
together. The redo sequence replaces the break-on-purpose route: the machine sees the red.

**Not adopted**:
- A separate agent writing tests: the only direct comparison found no gain at 3–8.5 times the
  tokens (Böckeler), as the README already records.
- An LLM-judged guard on every write (Probity, TDD Guard): R1.

## R11. Python toolchain for this repository

**Decision**: `pyproject.toml` with a uv dev group (ruff, mypy, pytest, pytest-timeout),
`[tool.uv] package = false`, `uv.lock` committed, mypy strict over `scripts/python` and
`tests/python`; CI runs ruff, mypy and pytest. Both files are export-ignored.

**Rationale**: the global rules' approved defaults for a Python project; the repository had no
Python before this feature, so the toolchain lands as its own task.

**Alternatives considered**: `unittest` without dev dependencies — no linter or type checker, which
the global rules require of Python code.
