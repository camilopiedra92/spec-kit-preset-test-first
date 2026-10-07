#!/usr/bin/env bash
# Runs scripts/python/ledger.py as Claude Code runs it -- `python3 <path>` with
# the PostToolUse JSON on stdin -- in scratch repositories, after writes made
# the way the agent makes them (a shell heredoc writing a test and its code).
# The units in tests/python cover each rule; this covers the script as a hook:
# its stdin, its exit status and stderr, and its cost per call (SC-003).
#
# Usage:  tests/ledger.sh        from the repository root
set -uo pipefail

PRESET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$PRESET/scripts/python/ledger.py"
fail=0
problem() {
  echo "FAIL: $*"
  fail=1
}

scratch_repo() {
  local repo=$1
  git init -q -b main "$repo"
  git -C "$repo" config user.email t@example.com
  git -C "$repo" config user.name T
  mkdir -p "$repo/tests" "$repo/src" "$repo/.specify"
  echo 'def test_a(): pass' > "$repo/tests/test_a.py"
  echo 'A = 1' > "$repo/src/a.py"
  printf '%s\n' '{"tests": ["tests/**"], "sources": ["src/**"], "run": "x {file} {junit}"}' \
    > "$repo/.specify/test-first.json"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m init
}

hook_input() {
  printf '{"cwd": "%s", "session_id": "s1", "tool_name": "Bash", "tool_use_id": "%s"}' "$1" "$2"
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# A test and its code written by one shell command land in one record.
repo=$work/heredoc
scratch_repo "$repo"
bash -c "cat > '$repo/tests/test_b.py' <<'PY'
def test_b(): assert True
PY
cat > '$repo/src/b.py' <<'PY'
B = 2
PY"
hook_input "$repo" toolu_heredoc | python3 "$HOOK" 2> "$work/stderr"
status=$?
[ "$status" -eq 0 ] || problem "hook exited $status after a heredoc write: $(cat "$work/stderr")"
files=$(git -C "$repo" ls-tree -r --name-only refs/worktree/test-first/ledger 2> /dev/null)
grep -qx 'tests/test_b.py' <<< "$files" || problem "the record lacks tests/test_b.py"
grep -qx 'src/b.py' <<< "$files" || problem "the record lacks src/b.py"
[ "$(git -C "$repo" rev-list --count refs/worktree/test-first/ledger 2> /dev/null)" = 1 ] ||
  problem "one call should add one record"

# SC-003: a record costs at most 100 ms per call -- the median of eleven calls of
# the whole hook process, each after a change, on 1,000 tracked files and no
# untracked ones. The machine is printed beside the result. SC-003 is defined on
# the development machine; on a shared CI runner a wall-clock threshold fails on
# its neighbours' load (observed 58-110 ms for the same code here at a load
# average of 3.2), so CI reports the figure without failing on it.
repo=$work/thousand
scratch_repo "$repo"
for i in $(seq 1 998); do echo "x = $i" > "$repo/src/m$i.py"; done
git -C "$repo" add -A && git -C "$repo" commit -q -m files
# Timed from one process, so no timer's own start-up is counted.
cat > "$work/time.py" << 'PY'
import json, statistics, subprocess, sys, time
from pathlib import Path
repo, hook = Path(sys.argv[1]), sys.argv[2]
times = []
for i in range(1, 12):
    (repo / "src" / "a.py").write_text(f"A = {i}\n")
    payload = json.dumps(
        {"cwd": str(repo), "session_id": "s", "tool_name": "Bash", "tool_use_id": f"t{i}"}
    )
    start = time.monotonic()
    subprocess.run([sys.executable, hook], input=payload, text=True, check=True)
    times.append(round((time.monotonic() - start) * 1000))
print(int(statistics.median(times)), " ".join(map(str, times)))
PY
read -r median times < <(python3 "$work/time.py" "$repo" "$HOOK")
echo "record on $(git -C "$repo" ls-files | wc -l | tr -d ' ') tracked files: median ${median} ms of" \
  "${times} ($(uname -sm), $(sysctl -n hw.model 2> /dev/null || uname -n))"
if [ "$median" -gt 100 ]; then
  if [ -n "${CI:-}" ]; then
    echo "note: over SC-003's 100 ms on a CI runner; enforced on the development machine"
  else
    problem "a record took ${median} ms, over SC-003's 100 ms"
  fi
fi

[ "$fail" -eq 0 ] && echo "ok: ledger"
exit "$fail"
