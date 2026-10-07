# Contract: the audit

```bash
python3 .specify/presets/test-first/scripts/python/audit.py [--base <rev>] [--deadline <seconds>]
```

- `--base`: default `git merge-base HEAD <default branch>` (the branch `origin/HEAD` names, else
  `main`).
- `--deadline`: per replay, whole seconds, default 300; passed to `run-bounded.sh`.
- Reads only git objects, the ledger and `.specify/test-first.json`; writes only in a temporary
  directory, removed on exit (its scratch worktree included).

Output, stdout: one line per new test, `<verdict> <test id> <record> <tool> <call>`, grouped by
verdict, then a summary line `audit: <n> new tests: <count per verdict>; <pass|FAIL>`.

Exit: 0 when every new test is `red` or `predates`; 1 otherwise; 2 on a usage or configuration
error (no ledger, no configuration, no base).
