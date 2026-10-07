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

# Finds what a case left behind by the sleep's own command line (the runner's
# also names it), then kills everything naming it, the shell that would start
# the next sleep included, so one failure does not leak into the next case or
# outlive the test.
leftover() {
  if pgrep -f "^sleep $1" > /dev/null; then
    pkill -KILL -f "sleep $1"
    return 0
  fi
  return 1
}

# The runner under test, given 15 seconds: a broken runner must fail a case,
# not hang the suite. 200 means it was killed at that bound.
rb() {
  local runner tenths=0
  bash "$RUN" "$@" &
  runner=$!
  while kill -0 "$runner" 2> /dev/null; do
    if [ $tenths -ge 150 ]; then
      kill -KILL "$runner"
      wait "$runner" 2> /dev/null
      return 200
    fi
    sleep 0.1
    tenths=$((tenths + 1))
  done
  wait "$runner" 2> /dev/null
}

expect() { # name expected-status actual-status
  [ "$3" = "$2" ] || problem "$1: exit $3, expected $2"
}

out=$(bash "$RUN" 2>&1)
expect "no arguments" 2 $?
grep -q usage <<< "$out" || problem "no arguments: no usage line"

# A deadline sleep rejects would fire at once and read as caught.
# macOS sleep rejects 2147483648 and above.
for bad in 0 -5 abc 5min 1.5 9999999999; do
  rb "$bad" true 2> /dev/null
  expect "deadline '$bad'" 2 $?
done

rb 5 true
expect "passing command" 0 $?

rb 5 sh -c 'exit 3'
expect "failing command keeps its status" 3 $?

start=$SECONDS
rb 1 sleep 9101
expect "hang" 124 $?
[ $((SECONDS - start)) -le 3 ] || problem "hang: took $((SECONDS - start))s on a 1s deadline"
leftover 9101 && problem "hang: the command outlived the deadline"

# A leader that answers SIGTERM with exit 0 must not read as a pass.
rb 1 sh -c 'trap "exit 0" TERM; sleep 9102 & wait'
expect "leader exits 0 on SIGTERM" 124 $?
leftover 9102 && problem "leader exits 0 on SIGTERM: its child survived"

rb 1 sh -c 'sh -c "trap \"\" TERM; sleep 9103; sleep 9103" & wait'
expect "child ignores SIGTERM" 124 $?
leftover 9103 && problem "child ignores SIGTERM: survived the deadline"

# The leader itself survives SIGTERM: only the grace period's SIGKILL ends it.
start=$SECONDS
rb 1 sh -c 'trap "" TERM; sleep 9107; sleep 9107'
expect "leader ignores SIGTERM" 124 $?
[ $((SECONDS - start)) -le 9 ] || problem "leader ignores SIGTERM: took $((SECONDS - start))s"
leftover 9107 && problem "leader ignores SIGTERM: survived the grace period"

rb 5 sh -c 'sleep 9104 & exit 1'
expect "exits on time, child left running" 1 $?
leftover 9104 && problem "exits on time: its background child survived"

err=$(rb 1 bash -c 'sleep 9105 | cat' 2>&1 > /dev/null)
expect "pipeline" 124 $?
# Bash's report of a job it killed reads as the suite being killed.
[ -z "$err" ] || problem "pipeline: stderr has the runner's job reports: $err"
leftover 9105 && problem "pipeline: a stage survived"

# A child forked while the group is being killed is not in the group the kill
# saw; one kill left one behind in about a quarter of runs on macOS.
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  rb 5 bash -c '(while :; do sleep 9108 & kill -9 $! 2> /dev/null; done) & sleep 0.2; exit 0'
done
sleep 1
leftover 9108 && problem "child forked during the kill: survived"

# Under a terminal the command is a background job, and one that reads stdin
# is stopped by SIGTTIN until the deadline. `script` gives it a terminal.
if [ "$(uname)" = Darwin ]; then
  with_tty() { script -q /dev/null "$@"; }
else
  with_tty() { script -qec "$(printf '%q ' "$@")" /dev/null; }
fi
start=$SECONDS
with_tty bash "$RUN" 5 sh -c 'read -r line; exit 0' < /dev/null > /dev/null
expect "reads stdin under a terminal" 0 $?
[ $((SECONDS - start)) -le 3 ] || problem "reads stdin under a terminal: took $((SECONDS - start))s"

# The shell an agent's tool runs commands in, with no terminal: zsh rejects
# `set -m` there, which is why the runner is a bash script.
if command -v zsh > /dev/null; then
  zsh -c "bash '$RUN' 5 true" < /dev/null
  expect "under zsh -c with no terminal" 0 $?
else
  echo "skip: zsh not installed"
fi

# Killed from outside, as a tool's timeout or a kill by name would. Job
# control gives the runner a group of its own, so it receives INT and QUIT
# as from a terminal: a background job without it starts with both ignored.
set -m
for signal in TERM INT HUP QUIT; do
  bash "$RUN" 30 sh -c 'sleep 9106 & wait' 2> /dev/null &
  runner=$!
  sleep 1
  kill -"$signal" "$runner"
  wait "$runner" 2> /dev/null
  sleep 1
  leftover 9106 && problem "runner killed by $signal: the command survived it"
done
# Terminated, it passes SIGTERM on before any SIGKILL, as its deadline does, so the command can
# clean up: git removes its lock files on SIGTERM and cannot on SIGKILL.
cleaned=$(mktemp -u)
bash "$RUN" 30 sh -c "trap 'echo done > $cleaned; exit 0' TERM; sleep 9108 & wait" 2> /dev/null &
runner=$!
sleep 1
kill -TERM "$runner"
wait "$runner" 2> /dev/null
sleep 1
[ -e "$cleaned" ] || problem "runner terminated: the command got no SIGTERM to clean up with"
rm -f "$cleaned"
leftover 9108 && problem "runner terminated: the command survived it"

# A second signal, or a SIGKILL, while it waits out the grace period must not leave a command
# that ignores SIGTERM running past its bounds: the watchdog still holds the deadline.
for second in TERM KILL; do
  start=$SECONDS
  bash "$RUN" 4 sh -c "trap '' TERM; sleep 9109; sleep 9109" 2> /dev/null &
  runner=$!
  sleep 1
  kill -TERM "$runner"
  sleep 1
  kill -"$second" "$runner"
  wait "$runner" 2> /dev/null
  # The deadline (4 s) and the grace period (5 s), and a second to spare.
  # pgrep only: `leftover` kills what it finds.
  while pgrep -f "^sleep 9109" > /dev/null && [ $((SECONDS - start)) -lt 11 ]; do sleep 0.5; done
  leftover 9109 && problem "runner terminated, then $second: the command outlived its bounds"
done
# Two signals back to back: the second can arrive before the first's handler has run. The
# runner must still return only once the command is gone. Timing-dependent, so repeated: about
# half of the pairs found the hole before the traps were made idempotent.
early=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  bash "$RUN" 30 sh -c "trap '' TERM INT HUP QUIT; sleep 9110; sleep 9110" 2> /dev/null &
  runner=$!
  sleep 1
  for signal in TERM TERM; do kill -"$signal" "$runner" 2> /dev/null; done
  wait "$runner" 2> /dev/null
  pgrep -f "^sleep 9110" > /dev/null && early=$((early + 1))
  pkill -KILL -f "sleep 9110"
done
[ "$early" -eq 0 ] || problem "runner terminated twice at once: returned with the command alive, $early of 10"
set +m

[ "$fail" -eq 0 ] && echo "ok: run-bounded"
exit "$fail"
