#!/usr/bin/env bash
# Puts the current repository's test suite behind a Claude Code Stop hook, as
# one commit of its own: a turn that ends on a red suite is blocked once, with
# the failure, so Claude has been shown it before the turn can end.
#
# Usage:  install-stop-gate.sh <test command> [args...]   from the repository root
#         e.g. bash .specify/presets/test-first/scripts/bash/install-stop-gate.sh uv run pytest -q
#
# /speckit-implement runs it the first time it sees the suite green with no
# gate installed, so nobody has to remember to.
#
# The suite runs at every stop, so the command should be one that is quick to
# run every turn; a slow suite gets a fast subset here and stays whole in CI.
#
# Why a hook: test-first otherwise rests on instructions and on the per-story
# review, and the Claude Code docs say an unattended run needs a deterministic
# gate (code.claude.com/docs/en/best-practices, "Give Claude a way to verify
# its work"). Observed on Claude Code 2.1.290: a Stop hook fires and blocks
# under `claude -p` too, and the next stop of that turn arrives with
# stop_hook_active true.
#
# The hook blocks once per turn and lets the next stop through. A gate with no
# way out is the pressure under which agents edit tests to pass (ImpossibleBench,
# arXiv 2510.20270); with one, a test that cannot pass honestly gets reported.
# The hook is written into the repository rather than pointing here, so every
# clone, on any machine, runs the same gate.
#
# It runs the suite every time rather than skipping an unchanged tree. A skip
# was tried and taken out: two independent reviews found a red suite let
# through by edits it could not see (submodules, nested repositories,
# skip-worktree entries), and each fix found another.
set -euo pipefail

[ "$#" -gt 0 ] || {
  echo "usage: install-stop-gate.sh <test command> [args...]" >&2
  exit 1
}
top=$(git rev-parse --show-toplevel 2> /dev/null) || {
  echo "install-stop-gate: not inside a git repository" >&2
  exit 1
}
if [ "$top" != "$(pwd -P)" ]; then
  echo "install-stop-gate: run it from the repository root, $top" >&2
  exit 1
fi
hook=.claude/hooks/stop-gate.sh
settings=.claude/settings.json
runner=.specify/presets/test-first/scripts/bash/run-bounded.sh
# -L as well: a dangling symlink is not -e, and writing through it would land
# the hook wherever it points. A hook with no Stop entry is how a repository
# turns the gate off, so this refusal is also what keeps it off.
if [ -e "$hook" ] || [ -L "$hook" ]; then
  echo "install-stop-gate: $hook already exists; edit its TEST_COMMAND to change the command" >&2
  exit 1
fi
# The hook runs the suite through the preset's runner, at the path an
# installed preset is committed under, so the gate keeps its deadline in every
# clone and a preset upgrade upgrades the runner.
if [ ! -f "$runner" ]; then
  echo "install-stop-gate: $runner is missing; the gate runs the suite through it" >&2
  exit 1
fi
if ! git ls-files --error-unmatch "$runner" > /dev/null 2>&1; then
  echo "install-stop-gate: $runner is not committed, so other clones would not have it; commit the preset first" >&2
  exit 1
fi
# Written through, a symlinked settings.json would change a file outside this
# repository and leave the one git tracks, the link, as it was.
if [ -L "$settings" ]; then
  echo "install-stop-gate: $settings is a symlink; the gate needs a settings.json of its own" >&2
  exit 1
fi
if ! git diff --cached --quiet; then
  echo "install-stop-gate: something is already staged, and it would land in this commit" >&2
  exit 1
fi
# The commit takes settings.json whole, so anything uncommitted in it would
# ride along under this commit's message. A skip-worktree or assume-unchanged
# entry hides such changes from git diff and keeps the new file out of the
# commit, so it is refused too.
if [ -e "$settings" ] && ! git ls-files --error-unmatch "$settings" > /dev/null 2>&1; then
  echo "install-stop-gate: $settings is not committed; commit or remove it first" >&2
  exit 1
fi
if git ls-files -v -- "$settings" | grep -qE '^([a-z]|S) '; then
  echo "install-stop-gate: $settings is marked skip-worktree or assume-unchanged; clear that first" >&2
  exit 1
fi
if ! git diff --quiet -- "$settings"; then
  echo "install-stop-gate: $settings has uncommitted changes; commit or discard them first" >&2
  exit 1
fi
# One path per call: check-ignore takes --quiet with a single pathname only.
if git check-ignore -q "$hook" || git check-ignore -q "$settings"; then
  echo "install-stop-gate: $hook or $settings is ignored by git (.gitignore, info/exclude or core.excludesFile), so the gate could not be committed" >&2
  exit 1
fi
# Read and merged before anything is written: an unreadable settings.json
# stops here, with nothing to undo. jq rewrites the file in its own layout.
# shellcheck disable=SC2016  # $CLAUDE_PROJECT_DIR is expanded by Claude Code, not here
entry='{"hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stop-gate.sh", "timeout": 600}]}'
if [ -e "$settings" ]; then
  # An object, checked first: jq reads an empty file as no input and prints
  # nothing, which would commit an empty settings.json.
  if ! jq -e 'type == "object"' "$settings" > /dev/null 2>&1 ||
    ! merged=$(jq --argjson entry "$entry" '.hooks.Stop += [$entry]' "$settings"); then
    echo "install-stop-gate: $settings is not a JSON object" >&2
    exit 1
  fi
  # The hook file gone but its entry left: a second entry would run the suite
  # twice at every stop.
  if jq -e '[.hooks.Stop[]?.hooks[]?.command | strings | select(contains(".claude/hooks/stop-gate.sh"))] | length > 0' \
    "$settings" > /dev/null; then
    echo "install-stop-gate: $settings already has a Stop entry for $hook; remove it or restore the hook" >&2
    exit 1
  fi
else
  merged=$(jq -n --argjson entry "$entry" \
    '{"$schema": "https://json.schemastore.org/claude-code-settings.json", hooks: {Stop: [$entry]}}')
fi
# The hook blocks every turn whose suite is red, so a suite that is red today
# would block every turn from the first one.
if ! out=$("$@" 2>&1); then
  printf '%s\n' "$out" | tail -n 20 >&2
  echo "install-stop-gate: the suite is red; make it green before gating on it" >&2
  exit 1
fi

# From here on a failure (a held index lock, a commit hook that refuses) puts
# the repository back as it was, so the next run is not refused by a hook file
# this one left behind. Only directories this run created are removed, deepest
# first.
committed=0
made_dirs=()
for d in .claude .claude/hooks; do
  [ -d "$d" ] || made_dirs=("$d" "${made_dirs[@]+"${made_dirs[@]}"}")
done
undo() {
  local d
  [ "$committed" -eq 1 ] && return
  git reset -q -- "$hook" "$settings" 2> /dev/null || true
  rm -f "$hook"
  if git ls-files --error-unmatch "$settings" > /dev/null 2>&1; then
    git checkout -q -- "$settings"
  else
    rm -f "$settings"
  fi
  for d in "${made_dirs[@]+"${made_dirs[@]}"}"; do rmdir "$d" 2> /dev/null || true; done
}
trap undo EXIT

# Each argument in single quotes, a quote inside one closed and reopened
# around an escaped quote: nothing in it is expanded when the hook runs, and
# the commit shows the command as a shell reads it back. printf %q is not used
# because bash 3.2 leaves a leading ~ unquoted, and the quote and its
# replacement sit in variables because bash 3.2 misparses quotes written
# inside ${var//...}.
quote="'"
escaped="'\\''"
words=
for arg in "$@"; do
  words="$words${words:+ }'${arg//$quote/$escaped}'"
done

mkdir -p .claude/hooks
{
  cat << 'EOF'
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

EOF
  printf 'TEST_COMMAND=(%s)\n' "$words"
  cat << 'EOF'
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
log=$(mktemp) || exit 0
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
    echo "below shows how far it got, and a verbose run names each test as it starts."
  else
    echo "Stop gate: the test suite is red (${TEST_COMMAND[*]})."
  fi
  tail -n 40 "$log"
  echo "Make it green by fixing the code. If a test is what is wrong, or cannot"
  echo "pass without contradicting the spec, say which test and why in your final"
  echo "message instead of changing it to pass."
} >&2
exit 2
EOF
} > "$hook"
chmod +x "$hook"
printf '%s\n' "$merged" > "$settings"

# Only these two paths, whatever else is staged by now (the suite ran since
# the staged check).
git add "$hook" "$settings"
# A commit hook's own output does not say what it refused, and a commit-msg
# policy will refuse every attempt; the caller needs to know which it was.
if ! git commit -q -m "Gate the end of every Claude turn on the test suite" \
  -m "Written by install-stop-gate: a Stop hook runs \`$words\` and blocks a red turn once." \
  -m "To turn it off, remove its entry under hooks.Stop in .claude/settings.json and keep $hook: deleting it makes /speckit-implement install the gate again." \
  -- "$hook" "$settings"; then
  echo "install-stop-gate: the commit was refused, by a pre-commit or commit-msg hook if" >&2
  echo "                   its output is above; nothing is left behind" >&2
  exit 1
fi
committed=1
echo "install-stop-gate: committed $hook and $settings"
