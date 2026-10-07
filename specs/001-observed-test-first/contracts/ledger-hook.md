# Contract: the ledger hook

Installed entries in `.claude/settings.json`:

```json
{"hooks": {
  "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command",
    "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.specify/presets/test-first/scripts/python/ledger.py"}]}],
  "Stop": [{"hooks": [{"type": "command",
    "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.specify/presets/test-first/scripts/python/audit.py --stop"}]}]
}}
```

## PostToolUse: `ledger.py`

Input: Claude Code's `PostToolUse` JSON on stdin; fields read: `cwd`, `session_id`, `agent_id`
(optional), `tool_name`, `tool_use_id`.

1. Resolve the git worktree of `cwd`. Not in a git worktree, or its root has no
   `.specify/test-first.json`: exit 0, no output.
2. Snapshot the worktree (data-model.md, Record), with `branch` and `head`; if the tree equals the
   newest record's: exit 0.
3. Append a record and move `refs/worktree/test-first/ledger` atomically (retry on a race).
4. If the change is mixed: exit 2; stderr names the test paths and the source paths, and says that
   a test added or changed in this call together with the code that satisfies it will fail the
   audit, and how to redo it.
5. Otherwise exit 0, no output.

Any failure in steps 2–3 (a git error, a malformed configuration): exit 2 with the error on stderr;
the worktree and the real index are never modified.

## Stop: `audit.py --stop`

Input: Claude Code's `Stop` JSON on stdin; fields read: `cwd`, `session_id`, `stop_hook_active`.

1. As step 1 above; also exit 0 when HEAD is detached or on the default branch, or
   `stop_hook_active` is true (one block per turn). Claude Code runs every Stop hook of a stop in
   parallel, so the 1.x Stop gate's block does not hide this audit's first run; but once any Stop
   hook has blocked, the rest of that turn's stops skip this audit, so a test born after that
   block is shown at the next turn, or by the story-close audit.
2. Snapshot the worktree as a record (`tool` = `Stop`) if it changed.
3. Run the audit (audit.md) within a budget of `--budget` seconds (default 120), each run under a
   60-second deadline: no new run starts after the budget is spent, and a run already stopped by a
   deadline at least that long is not retried; what is left is judged by a later turn or the
   story-close audit, from the memo.
4. If any new test has a failing verdict that is final before the end (data-model.md): exit 2;
   stderr lists those tests with their verdict, record and call, and the redo sequence.
5. Otherwise exit 0; when the budget ran out, stderr says how many births are not judged yet
   (shown to the user, not to Claude).

A configuration or git error: exit 2 with the error on stderr.
