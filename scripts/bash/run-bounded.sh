#!/usr/bin/env bash
# Runs a command in a process group of its own and kills the whole group when
# the command ends, when the deadline passes, or when this script is stopped.
# Exits with the command's status, or 124 when the deadline fired (GNU
# timeout's code), whatever the command answered to being stopped.
#
# Usage:  run-bounded.sh <seconds> <command> [args...]
#         e.g. bash .specify/presets/test-first/scripts/bash/run-bounded.sh 300 uv run pytest -q
#         A pipeline goes in as one command: ... 300 bash -c 'npm test 2>&1 | tail -20'
#
# The story review runs each wrong version through it. A wrong version can
# loop or grow without end, and stopping one process leaves its children
# running: in expense-split's story 2 review (2026-10-06) the Bash tool's
# timeout moved the run to the background, `subprocess.run(timeout=...)` and
# `pkill` each stopped one process, and the suite ran 13 hours, to 67 GB of
# swap. A bash script rather than a snippet, because the agent's shell may be
# zsh, which refuses `set -m` without a terminal.
#
# Ceilings: a process that starts a session of its own (setsid, a daemon)
# leaves the group and is out of reach, macOS having no cgroup to hold it; and
# under a terminal, a command that opens /dev/tty itself is still stopped
# until the deadline.
set -u

usage() {
  echo "usage: run-bounded.sh <seconds> <command> [args...]   seconds: 1 to 999999999" >&2
  exit 2
}
[ $# -ge 2 ] || usage
# Whole seconds, because that is all POSIX sleep takes, and at most 9 digits,
# because macOS sleep rejects 2147483648 and above: a value sleep rejects
# would make the watchdog fire at once and the run read as caught.
case $1 in
  '' | *[!0-9]* | 0* | ??????????*) usage ;;
esac
seconds=$1
shift
# A child that ignores SIGTERM gets this long before SIGKILL.
grace=5

# Under a terminal the command is a background job, and a read from the
# terminal would stop it (SIGTTIN) until the deadline.
[ ! -t 0 ] || exec < /dev/null

flags=$(mktemp -d) || exit 1
fired=$flags/fired
pid=
watchdog=
# One kill reaches the members that exist when it runs; a child forked at that
# instant survives it (on macOS, in about a quarter of runs of a fork loop).
# Repeated until the group is empty, capped because a leader not yet reaped
# still counts as a member.
kill_group() {
  local tries=0
  while kill -KILL -- "-$1" 2> /dev/null && [ $tries -lt 20 ]; do
    tries=$((tries + 1))
  done
}
terminated=
# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  [ -z "$watchdog" ] || kill_group "$watchdog"
  # Ended by a signal while the command runs: SIGTERM first and the grace period, as the
  # deadline does, so the command can clean up (git removes its lock files on SIGTERM, and
  # cannot on SIGKILL).
  if [ -n "$terminated" ] && [ -n "$pid" ] && kill -TERM -- "-$pid" 2> /dev/null; then
    local waited=0
    while kill -0 -- "-$pid" 2> /dev/null && [ "$waited" -lt $((grace * 10)) ]; do
      sleep 0.1
      waited=$((waited + 1))
    done
  fi
  # After the leader is gone its group can still hold children; SIGKILL
  # because they had their chance at SIGTERM, or ended on time and are
  # leftovers.
  [ -z "$pid" ] || kill_group "$pid"
  rm -rf "$flags"
}
# Each signal that ends the runner is turned into an exit, so the EXIT trap
# runs (bash would skip it on QUIT) and knows it was a signal. Nothing runs on KILL; the watchdog still enforces the
# deadline then.
trap cleanup EXIT
trap 'terminated=1; exit 143' TERM
trap 'terminated=1; exit 130' INT
trap 'terminated=1; exit 129' HUP
trap 'terminated=1; exit 131' QUIT

# Job control gives each background job its own process group, led by the
# job's first process, so $! names the group.
set -m
"$@" &
pid=$!
(
  sleep "$seconds"
  : > "$fired"
  kill -TERM -- "-$pid"
  sleep "$grace"
  kill -KILL -- "-$pid"
) 2> /dev/null &
watchdog=$!
# Quiets bash's report of how the job ended ("Terminated: 15"); the command's
# own stderr is unaffected. A runner stopped from outside still prints one.
wait "$pid" 2> /dev/null
status=$?
# Shut the watchdog before reading the flag, so it cannot fire in between.
# Both quieted: bash can report the killed job between the two.
{
  kill_group "$watchdog"
  wait "$watchdog"
} 2> /dev/null
watchdog=
[ ! -e "$fired" ] || exit 124
exit "$status"
