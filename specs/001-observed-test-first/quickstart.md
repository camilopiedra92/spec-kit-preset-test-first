# Quickstart: validating observed test-first

Prerequisites: `git`, `python3`, `jq`, `uv`, `specify` on PATH; run from the repository root.

1. Units: `uv run pytest` — green.
2. The hook end to end: `tests/ledger.sh` — a mixed call is reported, a test-only call is silent,
   an unchanged tree adds no record, a linked worktree keeps its own ledger, a subagent's call is
   recorded with its id.
3. The installer: `tests/install-ledger.sh` — each refusal leaves the repository unchanged; a
   successful run is one commit of two files.
4. The audit: `tests/audit.sh` — over replayed sequences in a scratch pytest project:
   - test, then code → `red`, exit 0 (SC-002);
   - test and code in one call → `born-with-code`, exit 1 (SC-001);
   - code, then test → `born-green`, exit 1 (SC-002);
   - a moved test → `predates`, exit 0;
   - import error, then stub, then code → `red`;
   - a replay that hangs → `not-judged`, exit 1, nothing left running.
5. Composition: commit, then `tests/compose.sh` — the fragments compose, the new scripts land where
   the implement fragment runs them, and no dev file is in the archive.
6. In a real project (renta): install with its configuration, make one test-only call and one mixed
   call, run the audit, read the verdicts; time a record (SC-003).
