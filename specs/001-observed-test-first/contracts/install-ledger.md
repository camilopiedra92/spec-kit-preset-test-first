# Contract: the installer

```bash
bash .specify/presets/test-first/scripts/bash/install-ledger.sh \
  --tests '<glob>'... --sources '<glob>'... --run '<command>'
```

Writes `.specify/test-first.json` and the two hook entries of [ledger-hook.md](ledger-hook.md)
(`hooks.PostToolUse` and `hooks.Stop`) in `.claude/settings.json`, keeping every other entry, and
commits exactly those two files as one commit. Refuses, exit 1, the repository unchanged, when: not
at the repository root with `.specify/`; HEAD is detached; no base resolves (data-model.md, Base —
HEAD on the default branch included);
anything is staged; `.claude/settings.json` exists and is untracked, tracked with uncommitted changes, ignored, not a
regular file or skip-worktree (it is created when absent); a
ledger entry already exists; a flag is missing or `--run` lacks `{file}` or `{junit}`; the test
globs match no tracked file; `jq` is missing; a commit hook rejects the commit.
