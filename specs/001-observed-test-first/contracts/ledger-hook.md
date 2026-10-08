# Contract: the ledger hook

Both run through `scripts/python/cli.py`, which checks the Python version before anything else:
on a `python3` older than 3.11 it exits 2 with `test-first: needs python3 >= 3.11, found <v>`, so
Claude is told instead of the hook failing on an import (research R3).

Installed entries in `.claude/settings.json`:

```json
{"hooks": {
  "PostToolUse": [{"matcher": "*", "hooks": [{"type": "command",
    "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.specify/presets/test-first/scripts/python/cli.py ledger"}]}],
  "Stop": [{"hooks": [{"type": "command", "timeout": 300,
    "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.specify/presets/test-first/scripts/python/cli.py audit --stop"}]}]
}}
```

## PostToolUse: `cli.py ledger`

Input: Claude Code's `PostToolUse` JSON on stdin; fields read: `cwd`, `session_id`, `agent_id`
(optional), `tool_name`, `tool_use_id`.

1. Resolve the git worktree of `cwd`. Not in a git worktree, or its root has no
   `.specify/test-first.json`: exit 0, no output.
2. Snapshot the worktree (data-model.md, Record), with `branch` and `head`, through a copy of
   the worktree's index in the system's temporary location (never in the repository), removed on
   exit; if the tree equals the newest record's: exit 0.
3. Append a record and move `refs/worktree/test-first/ledger` atomically, retrying a lost race up to
   five times. Before the worktree's first record, that name is made a symbolic ref to
   `refs/test-first/ledgers/<random id>`, after deleting the ledgers no worktree points at.
4. If the change is mixed: exit 2; stderr names the test paths and the source paths, and says that
   a test added or changed in this call together with the code that satisfies it will fail the
   audit, and how to redo it.
5. Otherwise exit 0, no output.

Any failure in steps 2–4 — a malformed configuration, a git error (a locked ref, a full disk), the
retries of step 3 exhausted: exit 2 with the error on stderr; the worktree and the real index are
never modified.

No `timeout` is set on this entry, so Claude Code's 600-second default applies; a snapshot takes
tens of milliseconds (research L7). A hook killed mid-run leaves the ref at the old or the new
record and at most unreachable objects, which `git gc` prunes; its temporary index stays in the
system's temporary location, outside the repository, for the system to clean; the next call's
record then carries the killed call's changes under the next call's name, which fails closed.
Killed before a worktree's first record, it can also leave the per-worktree name pointing at a
ledger not yet created, where the next record lands; or a prune cut short, some removed
worktrees' ledgers deleted and the rest left for the next ledger's creation. A worktree's name
that git cannot read stops the prune with an error rather than being taken for absent.

## Stop: `cli.py audit --stop`

Input: Claude Code's `Stop` JSON on stdin; fields read: `cwd`, `session_id`, `stop_hook_active`.

1. As step 1 above; also exit 0 when HEAD is detached or on the default branch, or
   `stop_hook_active` is true (one block per turn). Claude Code runs every Stop hook of a stop in
   parallel, so the 1.x Stop gate's block does not hide this audit's first run; but once any Stop
   hook has blocked, the rest of that turn's stops skip this audit, so a test born after that
   block is shown at the next turn, or by the story-close audit.
2. Snapshot the worktree as a record (`tool` = `Stop`) if it changed.
3. Run the audit (audit.md) within a budget of `--budget` seconds (default 120), each run under a
   60-second deadline. A load probe is a run like any other, so no run of either kind starts
   after the budget: the worst case is the budget plus one run that started just before it ran
   out, with `run-bounded.sh`'s 5-second grace (185 s), plus git work outside any deadline — the
   snapshot, moving and cleaning the scratch worktree before each run, reading records — which
   takes seconds, inside the entry's `timeout` of 300 seconds — set because Claude Code cancels a hook that reaches
   its timeout and discards its output, so a timed-out Stop audit would let the turn end without a
   decision (research L7): no new run starts after the budget is spent, and a run already stopped by
   a deadline at least that long is not retried; what is left is judged by a later turn or the
   story-close audit, from the memo. The test files are taken most recently changed first, and a
   file the turn left unchanged lists its tests from its newest remembered run since it last
   changed instead of a new run at the newest record, so the budget goes to the turn's own files
   (and one run for each file whose tests are still red or not yet run, which the audit follows
   to the newest record); a test that appears without its file changing waits for the story-close
   audit.
4. If any new test has a failing verdict that is final before the end (data-model.md): exit 2;
   stderr lists those tests with their verdict, record and call, and each one's remedy from
   data-model.md's remedy table.
5. Otherwise exit 0, with no output. Births the budget left unjudged are judged by a later turn or
   the story-close audit; nothing about them reaches Claude at this stop.

A malformed configuration, no resolvable base, or a git error: exit 2 with the error on stderr —
one block per turn, like a failing verdict, so an audit that cannot run is never silent (FR-024).
