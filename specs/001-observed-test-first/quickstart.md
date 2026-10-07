# Quickstart: validating observed test-first

Prerequisites: `git`, `python3`, `jq`, `uv`, `specify` on PATH; run from the repository root.

1. Units: `uv run pytest` — green; `uv run ruff check`, `uv run mypy` — clean.
2. The hook end to end: `tests/ledger.sh` — a mixed call is reported, a test-only call is silent,
   an unchanged tree adds no record, a linked worktree keeps its own ledger, a subagent's call is
   recorded with its id, each record names its branch and HEAD.
3. The installer: `tests/install-ledger.sh` — each refusal leaves the repository unchanged; a
   successful run is one commit of two files holding both hook entries; no base resolving (HEAD on
   the default branch included) is a refusal.
4. The audit: `tests/audit.sh` — over replayed sequences in a scratch pytest project:
   - test, then code → `red`, exit 0 (SC-002);
   - test and code in one call → `born-with-code`, exit 1 (SC-001);
   - code, then test → `born-green`, exit 1 (SC-002);
   - test, a commit in its own call, then code → `red`;
   - a test-helper refactor while every test is green → verdicts unchanged;
   - a moved test that passes at the base → `predates`, exit 0;
   - tests renamed and merged in a test-only call → `refactored`, exit 0; the same call also adding
     a test for code written earlier → none refactored, exit 1;
   - an enum member renamed in code, renaming a parametrized test id → `refactored`;
   - a red test whose expected value is changed in a helper until it passes → `rewritten-to-green`;
   - behaviour written first in a template outside the source globs, tested later → `born-green`;
   - a red test rewritten in the call that adds its code → `rewritten-to-green`, exit 1 (SC-002);
   - a file that cannot load, then a stub, then code → `red`; then full code instead → `born-with-code`;
   - a typo that breaks a file for one call, then fixed → its tests are not born again (pytest and,
     where node is available, Vitest);
   - the redo sequence on a file's only test → `red`;
   - a branch merged or pulled in → its tests `unobserved`; a local merge into the default branch
     does not move the base;
   - an xfail test → `never-run`, listed, exit 0;
   - a shared fixture changed with the API in one call → the red test turning green is
     `not-judged`;
   - a test file left unloadable at the end → its tests `not-judged`, exit 1;
   - a test in a new file, then code → `red` (the commonest case, one extra run);
   - a test rewritten together with the code for a new case, replacing an accepted one →
     `born-with-code`, not `refactored`;
   - `git stash`, then `git stash pop` in another call → verdicts unchanged;
   - a test written and committed in one call → `unobserved`;
   - an audit killed mid-run, then rerun → no scratch worktree left registered;
   - an exception that is the bug, then the fix → `red`;
   - a branch created, visited away from and rebased mid-feature → the same verdicts;
   - an environment that imports from the real worktree → a predates candidate is `born-green`;
   - a replay that hangs → `not-judged`, exit 1, nothing left running;
   - a second audit reruns nothing (memo).
5. The Stop entry: in the same scratch project, a turn with a born-with-code test is blocked once
   and the next stop passes; a turn ending on a red case is not blocked; time it (SC-004).
6. Composition: commit, then `tests/compose.sh` — the fragments compose, the new scripts land where
   the implement fragment runs them, and no dev file is in the archive.
7. In a real project (renta): install with its configuration, make one test-only call and one mixed
   call, end the turn, run the audit, read the verdicts; time a record (SC-003).
