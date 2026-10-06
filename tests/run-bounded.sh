#!/usr/bin/env bash
# Tests scripts/bash/run-bounded.sh against commands built to escape it: one
# that hangs, one whose leader turns SIGTERM into a clean exit, a child that
# ignores SIGTERM, a child left behind by a command that exits on time, a
# pipeline, and the runner itself being killed. Each leftover is found by a
# sleep length no other case uses, so a survivor shows up by name.
#
# Usage:  tests/run-bounded.sh        from the repository root
set -uo pipefail

PRESET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$PRESET/scripts/bash/run-bounded.sh"
fail=0

problem() {
  echo "FAIL: $*"
  fail=1
}

# Kills what a case left behind, so one failure does not leak into the next
# case or outlive the test.
leftover() {
  if pgrep -f "sleep $1" > /dev/null; then
    pkill -KILL -f "sleep $1"
    return 0
  fi
  return 1
}

expect() { # name expected-status actual-status
  [ "$3" = "$2" ] || problem "$1: exit $3, expected $2"
}

out=$(bash "$RUN" 2>&1)
expect "no arguments" 2 $?
grep -q usage <<< "$out" || problem "no arguments: no usage line"

bash "$RUN" 5 true
expect "passing command" 0 $?

bash "$RUN" 5 sh -c 'exit 3'
expect "failing command keeps its status" 3 $?

start=$SECONDS
bash "$RUN" 1 sleep 9101
expect "hang" 124 $?
[ $((SECONDS - start)) -le 3 ] || problem "hang: took $((SECONDS - start))s on a 1s deadline"
leftover 9101 && problem "hang: the command outlived the deadline"

# A leader that answers SIGTERM with exit 0 must not read as a pass.
bash "$RUN" 1 sh -c 'trap "exit 0" TERM; sleep 9102 & wait'
expect "leader exits 0 on SIGTERM" 124 $?
leftover 9102 && problem "leader exits 0 on SIGTERM: its child survived"

bash "$RUN" 1 sh -c 'sh -c "trap \"\" TERM; sleep 9103; sleep 9103" & wait'
expect "child ignores SIGTERM" 124 $?
leftover 9103 && problem "child ignores SIGTERM: survived the deadline"

bash "$RUN" 5 sh -c 'sleep 9104 & exit 1'
expect "exits on time, child left running" 1 $?
leftover 9104 && problem "exits on time: its background child survived"

bash "$RUN" 1 bash -c 'sleep 9105 | cat'
expect "pipeline" 124 $?
leftover 9105 && problem "pipeline: a stage survived"

# The shell an agent's tool runs commands in, with no terminal: zsh rejects
# `set -m` there, which is why the runner is a bash script.
if command -v zsh > /dev/null; then
  zsh -c "bash '$RUN' 5 true" < /dev/null
  expect "under zsh -c with no terminal" 0 $?
fi

# Killed from outside, as a tool's timeout or a kill by name would.
bash "$RUN" 30 sleep 9106 &
runner=$!
sleep 1
kill -TERM "$runner"
wait "$runner"
sleep 1
leftover 9106 && problem "runner killed: the command survived it"

[ "$fail" -eq 0 ] && echo "ok: run-bounded"
exit "$fail"
