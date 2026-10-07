# Contract: the installer

```bash
bash .specify/presets/test-first/scripts/bash/install-ledger.sh \
  --tests '<glob>'... --sources '<glob>'... --run '<command>'
```

Writes `.specify/test-first.json` and the hook entry of
[ledger-hook.md](ledger-hook.md) under `hooks.PostToolUse` in `.claude/settings.json`, and commits
exactly those two files as one commit. Refuses, exit 1, the repository unchanged, when: not at the
repository root with `.specify/`; anything is staged; `.claude/settings.json` is uncommitted,
ignored, a symlink or skip-worktree; a ledger entry already exists; a flag is missing or `--run`
lacks `{files}` or `{junit}`; the test globs match no tracked file; `jq` is missing; a commit hook
rejects the commit.
