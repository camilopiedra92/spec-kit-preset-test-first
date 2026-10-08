# Contract: the audit

```bash
python3 .specify/presets/test-first/scripts/python/cli.py audit [--base <rev>] [--deadline <seconds>]
python3 .specify/presets/test-first/scripts/python/cli.py audit --stop [--budget <seconds>]   # the Stop hook
```

- `--base`: default as data-model.md, Base: the merge base with the remote-tracking default
  branch, so a local merge into the default branch does not move it.
- `--deadline`: per run, whole seconds from 1 to 999999999 (`run-bounded.sh`'s range), default
  300 (60 under `--stop`); passed to `run-bounded.sh`.
- `--budget`: with `--stop` only, whole seconds from 0 (judge only from runs already made) to
  999999999, see
  [ledger-hook.md](ledger-hook.md).
- Seconds outside that range are a usage error.
- Takes a snapshot first (a record with `tool` = `audit` or `Stop`) when the worktree differs from
  the newest record, so edits made between calls are judged.
- Judges the current branch's effective history (data-model.md). Refuses, exit 2, on a detached
  HEAD, HEAD on the default branch, no ledger, no configuration or no base.
- Reads, and nothing else: its arguments (and, under `--stop`, the hook JSON on stdin); the
  worktree, only to snapshot it as the hook does; the ledger ref, `HEAD`, the default-branch refs,
  whether an `origin` remote exists, and `init.defaultBranch`; the worktree registry, to prune its
  own scratch worktrees; record messages and the trees they name and the base commit's tree, which
  it materializes for the configured command and never parses, except `.specify/test-first.json`;
  the JUnit files its runs write; and the memo. It never reads a file of a record as evidence —
  `tasks.md` included (FR-012). Writes only: the snapshot's record (git objects, the ledger
  ref), as the hook does; the memo; a temporary directory in the system's temporary location,
  removed on exit; and the scratch worktree's registration in the repository's common git
  directory, removed with it. At start it prunes scratch worktrees an earlier audit left
  registered (killed or crashed), so the repository is left as found.

Output, stdout: one line per new test, `<verdict> <test id> <record> <tool> <call>` — for a file no
run could read, its path in place of the test id (data-model.md, Verdict) — with `-` for
the three fields of a verdict that rests on no record of its own (`unobserved`, `never-run`, and a
`not-judged` whose reason is not one record's: a replay past its deadline, the budget, a file whose
tests no run could read), and for `<call>` of a record no tool call made (the install's, an
audit's own snapshot), followed for
`refactored` by the tests it replaced and for `born-green` by its reason; grouped by verdict, then
a summary line `audit: <n> new tests: <count per verdict>; <pass|FAIL>`. Each failing verdict ends
with its remedy, as data-model.md's remedy table gives it.

Exit: 0 when every new test is `red`, `predates`, `refactored` or `never-run`; 1 otherwise; 2 on a
usage or configuration error.
