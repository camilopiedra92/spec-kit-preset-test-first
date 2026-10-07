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

---

# Landscape and evidence (2026-10-07)

The research behind R1–R11, kept whole so a later session does not redo it. Sources were read on
2026-10-07 unless dated otherwise. **Verified** = read in the primary source or measured here;
**second-hand** = from search results or a summary, not opened.

## L1. What motivated the feature: the renta run on preset 1.6.0

Project renta (private), feature `001-bridge-adjudication`, implemented 2026-10-06/07 with this
preset at 1.6.0 and Spec Kit 1.1.0.

- `tasks.md`: 33 case bullets record a red run, 27 record "passed on first run" (grep of
  "passed on first run|passed against|passed first"), out of about 60 cases.
- Session transcript (Claude Code JSONL), analysed with a script that, for each Bash call running
  pytest, classified which files the same command wrote (test files `tests/…`, source `co/…`,
  detected by `cat >`, `p='…'` in `python3 - <<EOF`, `sed -i`, `printf >>`) and the run's outcome.
  Of the runs that wrote files: 22 test-only green, 20 code-then-test red, 15 code-only red,
  13 code-only green, **11 code-and-test (CT) green**, 9 test-only red, others below 5. Reading the
  11 CT-green commands: production code and its test written in one shell command, then run green
  — e.g. the `OneOf.nearest` tie rule with "a single option is its own nearest"; the DEFECT/KNOWLEDGE
  "exactly one side" rule with three tests ("10 passed"), recorded in tasks.md as "passed on first
  run (the side-count rule)". Verified.
- The 1.6.0 fragment allowed it: "A new test that passes on its first run has not been watched
  failing. Break the code it pins on purpose, watch the test fail for the expected reason, restore
  the code, and record that failure and that the behaviour already existed." It does not tell
  "existed before this task" from "written a moment ago". Verified.
- The agent edits through Bash heredocs and `python3 - <<EOF`, so any Edit/Write-only hook is blind
  to most writes. Verified in the transcript.

## L2. Spec Kit core (github/spec-kit v1.1.1, 2026-10-06)

- `spec-driven.md`, Article III: "This is NON-NEGOTIABLE: All implementation MUST follow strict
  Test-Driven Development. No implementation code shall be written before: 1. Unit tests are
  written 2. Tests are validated and approved by the user 3. Tests are confirmed to FAIL (Red
  phase)". It claims "The implementation template enforces test-first development"; no current
  template carries that order (grep of `templates/`).
- `templates/constitution-template.md`: TDD only as a commented example.
- `templates/tasks-template.md`: "Tests are OPTIONAL - only include them if explicitly requested";
  also "Write these tests FIRST, ensure they FAIL before implementation".
- `templates/commands/implement.md`: "Execute test tasks before their corresponding implementation
  tasks".
- Issues: #627 "TDD principles not followed" (agent writes all tests, sees red, implements
  everything) closed NOT_PLANNED as stale; #2634 (built-in red-green enforcement) closed
  NOT_PLANNED 2026-08-04, maintainer: "asking for tests is already supported you just have to
  request it", pointing at extensions.
- Extension hooks (`extensions.yml`, events `before_*`/`after_*`) are prompts: the agent is told to
  emit `EXECUTE_COMMAND:`. Nothing in core verifies red-before-green.
- Verified (research agent, primary repository, cloned).

## L3. Other spec-driven frameworks

| Framework | Stance on test-first | Enforcement |
|---|---|---|
| **Kiro** (kiro.dev/docs/specs/correctness, updated 2026-08-04) | Extracts correctness properties from EARS requirements; "generates hundreds or thousands of random test cases when you choose to run them"; "PBTs are optional by default"; admits "A property that is too weak … will pass while the real behavior is still wrong". Bugfix specs carry a property validating the bug exists. | Prompted. Hooks (`.kiro/hooks/`, shell or agent actions; PreToolUse can block) are the deterministic part; no TDD mode. Amazon Q's agent migrated into Kiro. |
| **OpenSpec** v1.14.1 | "Each task MUST state how to verify completion". Its docs on a community TDD schema: "OpenSpec only checks that artifacts exist, so enforce the gate with your own CI or hook." | None. |
| **BMAD** v6.12.1 | Dev agent prompted to "test-first discipline — red, green, refactor"; TEA's ATDD "emits these scaffolds with `test.skip()`". | Red never executed. |
| **obra/superpowers** v6.4.2 | Iron Law: "NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST … Write code before the test? Delete it." | Only a SessionStart hook injecting context: prompt only. |
| **TDD Guard → Probity** (nizos, v1.10.1) | PreToolUse block on writes; `enforceTdd` "Uses an AI validator … to judge the pending action against the transcript"; opt-in deterministic fast-path for a write adding exactly one test. TDD Guard's docs warn shell (`sed`/`echo`) bypasses it unless denied. | Trigger deterministic, verdict an LLM's; npm + TypeScript config. |
| **Aider** | `--test-cmd`/`--auto-test`: fixes on non-zero exit. | Green loop, no order. |
| **Cursor** | Hooks preToolUse/afterFileEdit/stop; exit 2 blocks, others fail open. | No TDD mechanism. |
| **Claude Code** | Best practices: "have one Claude write tests, then another write code to pass them"; hooks "are deterministic and guarantee the action happens"; Stop hook as deterministic gate; verification subagent "so the agent doing the work isn't the one grading it". | Mechanisms, no TDD policy. |
| **Tessl** | Current docs do not mention TDD; `[@test]` links seen only in registry tiles. | Second-hand. |
| **Copilot coding agent** | No TDD-specific mechanism found. | Not researched in depth. |

Verified except where marked.

## L4. Spec Kit community extensions evaluated (cloned, read in full)

- **d0whc3r/spec-kit-tdd v1.1.2** (5 stars, four releases all 2026-08-03): package is
  `extension.yml`, README, LICENSE, four prompt commands and four templates — **nothing executed**
  beyond Spec Kit invoking `before_implement: speckit.tdd.run`. Its rubric grades PROVEN when "the
  cycle log records the red command and its failure output" — the agent's own log — and "A commit
  that adds a source file and its test in one commit is normal". Its Phase 3 prescribes the same
  "break the implementation … confirm the test fails, then restore" route. Mutation testing is
  advice, gated by the agent's own verdict. Rejected.
- **schwichtgit/spec-gates v0.4.0** (3 stars, released 2026-10-06): real bash hooks with exit codes
  — protect-files (PreToolUse Write|Edit), validate-bash (PreToolUse Bash, 1,347 lines of regex),
  validate-pr, post-edit formatting, Stop `verify-quality.sh`, git hooks, CI projection, "canaries"
  (15 planted violations each gate must reject), attestations. **No red-before-green and no
  mutation testing.** Probes: `python3 - <<'EOF'` writing `src/calc.py` and `tests/test_calc.py`
  → allowed (rc 0); `sed -i` on source → allowed. Its 1,092 hook tests passed here (4m09s). Default
  commit rules block "Anthropic" and `\bClaude\b` (would reject Co-Authored-By lines). Rejected;
  ideas borrowed: canaries, and observing tree state instead of parsing commands.

## L5. Evidence on TDD with agents

- **Böckeler, "TDD inside the agent loop – theater or actual value?"** (martinfowler.com, 2026):
  three greenfield Python tasks, Sonnet generating, Opus judging; "more than once Opus ranked the
  non-TDD workflow solutions slightly higher"; "no meaningful difference in mutation scores";
  tokens 8.50× (small), 2.96× (medium), 4.89× (large); "a red test tells you the agent ran it and
  saw failure, not that the failure was for the right reason"; agents "skipped or faked the red
  step". She recommends mutation testing for regression quality. Small n.
- **arXiv 2607.05139** (Konstantinou, Tambon, Papadakis, July 2026): tests generated after faulty
  code detect fewer faults than tests generated independently, 14% vs 25% — error propagation.
  Independence of test from code is the mechanism.
- **Mathews & Nagappan, arXiv 2402.13521**: tests in the prompt +12.0 (GPT-4, MBPP), +8.5
  (HumanEval), +29.6 (Llama 3, MBPP).
- **TiCoder, arXiv 2404.10100**: test-driven intent clarification, +45.97% pass@1 within 5 user
  interactions (idealised user).
- **TDD-Bench Verified, arXiv 2412.02883**: 449 issues; TDD tests defined as fail-to-pass.
- **SWT-bench, arXiv 2406.12952**: generated reproduction tests double SWE-Agent's precision as a
  filter.
- **ImpossibleBench, arXiv 2510.20270**: cheating on Conflicting-SWEbench GPT-5 54%, Opus 4.1 50%;
  hiding tests cuts it to near zero; read-only tests particularly effective against Opus 4.1,
  whose main strategy is modifying tests; a `flag_for_human_intervention` exit cut GPT-5 54% → 9%
  (much less for Opus 4.1); LLM monitors caught 42–65%.
- **Agentic PBT, arXiv 2510.09907** (Maaz, DeVoe, Hatfield-Dodds, Carlini; Anthropic): 100 Python
  packages, 56% of reported bugs valid, 86% of the top 21; 3 merged patches incl. NumPy.
- **Meta ACH, arXiv 2501.12862**: mutation-guided test generation, 10,795 classes, 9,095 mutants,
  571 tests, 73% accepted by engineers; equivalent-mutant detector precision 0.79 / recall 0.47
  (0.95 / 0.96 with pre-processing).
- **Kent Beck, Canon TDD** (newsletter.kentbeck.com/p/canon-tdd): one case at a time from a test
  list that grows; turning the whole list into tests up front is a mistake.
- **Petrović & Ivanković, "State of Mutation Testing at Google"**, ICSE-SEIP 2018: mutants surfaced
  at code review on the changed code, not as a codebase score. Second-hand (cited, not reopened).

## L6. Deterministic checks that a test encodes new behaviour

- **SWE-bench, arXiv 2310.06770**: "we apply the PR's test content, and log the associated test
  results before and after the PR's other content is applied. We filter out task instances
  without at least one test where its status changes from a fail to pass"; it also excludes
  instances "with tests that invoke newly created functions" — the import-error case where a red
  proves nothing.
- No authoritative ready-made CI action for fail-to-pass was found; the practice is a short script.
- **Mutation tools for Python**: mutmut 3.8.0 (2026-09-12) — no diff mode, function-name globs
  (`mutmut run "module.func*"`), re-tests only functions whose source changed when `mutants/`
  persists, skips decorated functions other than a lone `@staticmethod`/`@classmethod`, and
  `__new__`/`__getattribute__`/`__setattr__`; statuses from `mutmut.stats.status_by_exit_code`
  (killed, survived, no tests, not checked, suspicious, skipped, timeout, caught by type check,
  segfault, check was interrupted by user). cosmic-ray 8.7.0 — `cr-filter-git` restricts to edited
  lines. pytest-gremlins 1.11.2 — content-hash cache, no diff flag. mutatest — no release since
  2022.

## L7. Measurements made in this session

- **Ledger snapshot cost**: temporary index copied from the worktree's, `git add -A`,
  `git write-tree`, on renta (860 tracked files): 0.04–0.05 s, three runs.
- **Claude Code hooks reference**: PostToolUse fires for subagents' tool calls with `agent_id`;
  exit 2 shows stderr to Claude and cannot block; matcher `*` matches every tool;
  `${CLAUDE_PROJECT_DIR}` stays at the original root, read `cwd` for worktrees; the transcript is
  written asynchronously and can lag. Verified (code.claude.com/docs/en/hooks).
- **renta mutation gate** (merged 2026-10-07, PR #59, `scripts/mutation_gate.py`): on renta main
  a7503cd, mutmut over all of `co/` with the 40 runnable `tests/co` files: 3,589 mutants, 2,653
  killed, 936 survived; of the survivors 593 message-only (AST rule), 322 behaviour, 21 not
  classified by the prototype. All of `co/` under the ci Hypothesis profile: 4.5 min wall, 28 min
  CPU; one touched method: 35–55 s. Three independent reviews found and closed: fail-open on
  statuses other than `survived`, a shared allowlist that broke the weekly run, "message" too
  broad (nested text, stored arguments), `async def` unread, deleted files misattributed. Python
  3.14 also surfaced SyntaxWarnings in `formulas` 1.3.4 (`v is 1.0`, `v is not ""`), fixed upstream
  in vinci1it2000/formulas#184 (open).

## L8. Synthesis

Practitioners and data converge: test-first order cannot be prompted into reliability (every
framework prompts it; Böckeler and Spec Kit #627 saw it faked); what buys fault detection is a
test independent of the code plus a mechanical oracle. Prompts carry intent — the case list, the
properties from the spec, a stop-and-report exit. The machine carries the checks: observe the tree
(not the commands) and apply fail-to-pass at each test's birth (this feature), and measure test
strength with mutation testing on the changed code (renta's gate). Not worth adopting: an LLM judge
on every write, micro-step ceremony (3–8.5× tokens, no measured gain), whole-repo mutation on every
change, red logs the agent writes itself.
