# Contract: the ledger hook

Installed entry in `.claude/settings.json`:

```json
{"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [{"type": "command",
  "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.specify/presets/test-first/scripts/python/ledger.py"}]}]}}
```

Input: Claude Code's `PostToolUse` JSON on stdin; fields read: `cwd`, `session_id`, `agent_id`
(optional), `tool_name`, `tool_use_id`.

Behaviour:

1. Resolve the git worktree of `cwd`. Not in a git worktree, or its root has no
   `.specify/test-first.json`: exit 0, no output.
2. Snapshot the worktree; if the tree equals the newest record's: exit 0.
3. Append a record and move `refs/worktree/test-first/ledger` atomically (retry on a race).
4. If the change is mixed: exit 2, stderr names the test paths and the source paths.
5. Otherwise exit 0, no output.

Any failure in steps 2–3 (a git error, a malformed configuration): exit 2 with the error on stderr;
the worktree and the real index are never modified.
