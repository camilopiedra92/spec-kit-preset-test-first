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
HOOK="$PRESET/scripts/python/cli.py"
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
hook_input "$repo" toolu_heredoc | python3 "$HOOK" ledger 2> "$work/stderr"
status=$?
[ "$status" -eq 0 ] || problem "hook exited $status after a heredoc write: $(cat "$work/stderr")"
files=$(git -C "$repo" ls-tree -r --name-only refs/worktree/test-first/ledger 2> /dev/null)
grep -qx 'tests/test_b.py' <<< "$files" || problem "the record lacks tests/test_b.py"
grep -qx 'src/b.py' <<< "$files" || problem "the record lacks src/b.py"
[ "$(git -C "$repo" rev-list --count refs/worktree/test-first/ledger 2> /dev/null)" = 1 ] ||
  problem "one call should add one record"

# The agent hears a call that changed tests and code together (FR-005, exit 2 shows stderr to
# Claude), and nothing about one that changed only tests.
repo=$work/told
scratch_repo "$repo"
hook_input "$repo" toolu_origin | python3 "$HOOK" ledger 2> /dev/null
echo 'def test_c(): pass' > "$repo/tests/test_c.py"
hook_input "$repo" toolu_tests | python3 "$HOOK" ledger 2> "$work/stderr"
status=$?
[ "$status" = 0 ] && [ ! -s "$work/stderr" ] || problem "a test-only call: exit $status: $(cat "$work/stderr")"
echo 'def test_d(): pass' > "$repo/tests/test_d.py"
echo 'D = 1' > "$repo/src/d.py"
hook_input "$repo" toolu_mixed | python3 "$HOOK" ledger 2> "$work/stderr"
status=$?
[ "$status" = 2 ] && grep -q 'tests/test_d.py' "$work/stderr" && grep -q 'src/d.py' "$work/stderr" ||
  problem "a mixed call: exit $status: $(cat "$work/stderr")"

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
times = {"code-only": [], "mixed": []}
for i in range(1, 23):
    kind = "mixed" if i % 2 == 0 else "code-only"
    (repo / "src" / "a.py").write_text(f"A = {i}\n")
    if kind == "mixed":
        (repo / "tests" / "test_a.py").write_text(f"def test_a(): assert {i}\n")
    payload = json.dumps(
        {"cwd": str(repo), "session_id": "s", "tool_name": "Bash", "tool_use_id": f"t{i}"}
    )
    start = time.monotonic()
    # A mixed call exits 2 by design; any other status is the hook failing.
    status = subprocess.run([sys.executable, hook, "ledger"], input=payload, text=True,
                            capture_output=True).returncode
    if status != (2 if kind == "mixed" else 0):
        sys.exit(f"{kind} call {i}: exit {status}")
    times[kind].append(round((time.monotonic() - start) * 1000))
for kind, ms in times.items():
    print(kind, int(statistics.median(ms)), " ".join(map(str, ms)))
PY
python3 "$work/time.py" "$repo" "$HOOK" > "$work/times" || problem "timing: $(cat "$work/times")"
for kind in code-only mixed; do
  read -r _ median times < <(grep "^$kind " "$work/times")
  if [ -z "${median:-}" ]; then
    problem "no $kind timing measured"
    continue
  fi
  echo "$kind record on $(git -C "$repo" ls-files | wc -l | tr -d ' ') tracked files: median ${median} ms" \
    "of ${times} ($(uname -sm), $(sysctl -n hw.model 2> /dev/null || uname -n))"
  if [ "$median" -gt 100 ]; then
    if [ -n "${CI:-}" ]; then
      echo "note: over SC-003's 100 ms on a CI runner; enforced on the development machine"
    else
      problem "a $kind record took ${median} ms, over SC-003's 100 ms"
    fi
  fi
done

# An older python3 -- the macOS one is 3.9 -- gets a message, not a traceback: the guard at the
# top of each script runs only if the whole file still parses there.
for command in ledger audit; do
  out=$(echo '{}' | uv run --quiet --isolated --no-project --python 3.9 python "$HOOK" "$command" 2>&1)
  status=$?
  [ "$status" = 2 ] && grep -q "needs python3 >= 3.11, found 3.9" <<< "$out" ||
    problem "cli.py $command under Python 3.9: exit $status: $out"
done

# The Stop hook keeps its one-block-per-turn rule there too: the stop that continues a turn
# already blocked goes through, or an old python3 would block every stop.
out=$(echo '{"stop_hook_active": true}' |
  uv run --quiet --isolated --no-project --python 3.9 python "$HOOK" audit --stop 2>&1)
status=$?
[ "$status" = 0 ] || problem "cli.py audit --stop under Python 3.9, a continued stop: exit $status: $out"

[ "$fail" -eq 0 ] && echo "ok: ledger"
exit "$fail"
