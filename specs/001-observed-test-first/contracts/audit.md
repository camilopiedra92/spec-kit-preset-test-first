# Contract: the audit

```bash
python3 .specify/presets/test-first/scripts/python/cli.py audit [--base <rev>] [--deadline <seconds>]
python3 .specify/presets/test-first/scripts/python/cli.py audit --stop [--budget <seconds>]   # the Stop hook
```

- `--base`: default as data-model.md, Base: the merge base with the remote-tracking default
  branch, so a local merge into the default branch does not move it.
- `--deadline`: per run, whole seconds, default 300 (60 under `--stop`); passed to
  `run-bounded.sh`.
- `--budget`: with `--stop` only, see [ledger-hook.md](ledger-hook.md).
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

Output, stdout: one line per new test, `<verdict> <test id> <record> <tool> <call>`, with `-` for
the three fields of `unobserved`, which rests on no record of its own, followed for
`refactored` by the tests it replaced and for `born-green` by its reason; grouped by verdict, then
a summary line `audit: <n> new tests: <count per verdict>; <pass|FAIL>`. Each failing verdict ends
with its remedy, as data-model.md's remedy table gives it.

Exit: 0 when every new test is `red`, `predates`, `refactored` or `never-run`; 1 otherwise; 2 on a
usage or configuration error.
