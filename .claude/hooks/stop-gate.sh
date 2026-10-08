#!/usr/bin/env bash
# Claude Code Stop hook written by the test-first Spec Kit preset
# (github.com/camilopiedra92/spec-kit-preset-test-first,
# scripts/bash/install-stop-gate.sh), which explains the design. When the
# suite is red, the first stop of a turn is blocked with the failure and the
# next stop goes through, so Claude is shown the failure and a test that cannot
# pass honestly gets reported instead of forced green.
#
# To turn it off, remove its entry under hooks.Stop in .claude/settings.json
# and keep this file: deleting it makes /speckit-implement install the gate
# again.
set -uo pipefail

TEST_COMMAND=('uv' 'run' 'pytest' '-q')
# Seconds the suite gets before its whole process group is killed: with the
# runner's 5-second grace, under the 600 Claude Code gives this hook.
DEADLINE=540
RUNNER=.specify/presets/test-first/scripts/bash/run-bounded.sh

cd "${CLAUDE_PROJECT_DIR:?}" || exit 0
grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true' && exit 0
if [ ! -f "$RUNNER" ]; then
  echo "Stop gate: $RUNNER is missing, so the suite cannot run under its deadline." >&2
  echo "Restore the test-first preset and commit it, or turn this gate off as its file says." >&2
  exit 2
fi
log=$(mktemp) || {
  echo "Stop gate: could not create a temporary file for the suite's output, so the suite did not run." >&2
  exit 2
}
trap 'rm -f "$log"' EXIT
# To a file rather than through $(...): a process that left the suite's group
# (setsid) keeps running out of the runner's reach, and would hold a pipe, and
# with it this stop, open past the deadline.
bash "$RUNNER" "$DEADLINE" "${TEST_COMMAND[@]}" > "$log" 2>&1
status=$?
[ "$status" -eq 0 ] && exit 0
{
  if [ "$status" -eq 124 ]; then
    echo "Stop gate: the test suite did not finish in ${DEADLINE}s, or exited 124 itself"
    echo "(${TEST_COMMAND[*]}). A test that hangs needs a time limit of its own; the output"
    echo "below shows how far it got; a verbose run (pytest -v) names the test it was on."
  else
    echo "Stop gate: the test suite is red (${TEST_COMMAND[*]})."
  fi
  tail -n 40 "$log"
  echo "Make it green by fixing the code. If a test is what is wrong, or cannot"
  echo "pass without contradicting the spec, say which test and why in your final"
  echo "message instead of changing it to pass."
} >&2
exit 2
