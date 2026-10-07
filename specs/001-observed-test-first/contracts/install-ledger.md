# Contract: the installer

```bash
python3 .specify/presets/test-first/scripts/python/cli.py install \
  --tests '<glob>'... --sources '<glob>'... --run '<command>'
```

Writes `.specify/test-first.json` and the two hook entries of [ledger-hook.md](ledger-hook.md)
(`hooks.PostToolUse` and `hooks.Stop`) in `.claude/settings.json`, keeping every other entry, and
commits exactly those two files as one commit; then records the worktree as the ledger's first
record (`tool` = `install`, data-model.md, origin), so the first tool call's record is a change.
Refuses, exit 1, the repository unchanged, when: not
at the repository root with `.specify/`; HEAD is detached; no base resolves (data-model.md, Base —
HEAD on the default branch included); anything is staged; `.claude/settings.json` exists and is
untracked, tracked with uncommitted changes, ignored, not a regular file or skip-worktree (it is
created when absent); a ledger entry already exists; a flag is missing or `--run` lacks `{file}` or
`{junit}`; a glob git cannot use as a pathspec (outside the repository); the test globs match no
tracked file; `.claude/` or `.specify/` is a symlink; `settings.json` is not a settings object
(its hooks an object of events, each a list of matcher objects, each command a string); a commit
hook rejects the commit, or does not finish within the commit's 300-second deadline (the commit
runs under `run-bounded.sh`); the preset's `run-bounded.sh` is missing; it is terminated (SIGTERM,
SIGHUP) during its commit. If the ledger's
first record fails after the commit, it exits 1 saying the commit stands and the first tool
call's record will be the origin. A `python3` older
than 3.11 is refused by `cli.py` before any of these (ledger-hook.md). The installer is Python, in
the same package as the hook and the audit, so the base, the configuration's validation and the
globs' matching are the audit's own code, not a second copy (research R16).
