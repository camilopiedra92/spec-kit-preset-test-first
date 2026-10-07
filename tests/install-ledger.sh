#!/usr/bin/env bash
# Runs the installer as a project runs it -- `python3 <installed path>/cli.py install` from the
# repository root -- in a scratch project with the preset's scripts where an installed preset puts
# them, then runs each hook entry it committed the way Claude Code does: its command string through
# a shell, with CLAUDE_PROJECT_DIR set and the hook JSON on stdin. The units in
# tests/python/test_install.py cover each refusal; this covers the entry point, the commit and
# whether the committed commands run.
#
# Usage:  tests/install-ledger.sh        from the repository root
set -uo pipefail

PRESET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
problem() {
  echo "FAIL: $*"
  fail=1
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

repo=$work/project
git init -q -b main "$repo"
git -C "$repo" config user.email t@example.com
git -C "$repo" config user.name T
mkdir -p "$repo/tests" "$repo/src" "$repo/.specify/presets/test-first"
cp -R "$PRESET/scripts" "$repo/.specify/presets/test-first/scripts"
echo 'def test_a(): pass' > "$repo/tests/test_a.py"
echo 'A = 1' > "$repo/src/a.py"
git -C "$repo" add -A
git -C "$repo" commit -q -m init
install=(python3 .specify/presets/test-first/scripts/python/cli.py install
  --tests 'tests/**' --sources 'src/**'
  --run "python3 $PRESET/tests/python/fake_runner.py {file} {junit}")

# On the default branch: refused, exit 1, the repository as it was.
before=$(git -C "$repo" status --porcelain --ignored; git -C "$repo" rev-parse HEAD)
out=$(cd "$repo" && "${install[@]}" 2>&1)
status=$?
[ "$status" -eq 1 ] || problem "on the default branch the installer exited $status: $out"
grep -q "default branch" <<< "$out" || problem "the refusal does not say why: $out"
[ "$(git -C "$repo" status --porcelain --ignored; git -C "$repo" rev-parse HEAD)" = "$before" ] ||
  problem "a refusal changed the repository"

# On a feature branch: one commit of the two files.
git -C "$repo" checkout -q -b feat
out=$(cd "$repo" && "${install[@]}" 2>&1) || problem "the install failed: $out"
[ "$(git -C "$repo" show --name-only --format= HEAD | sort | tr '\n' ' ')" = \
  ".claude/settings.json .specify/test-first.json " ] ||
  problem "the commit holds: $(git -C "$repo" show --name-only --format= HEAD)"
[ -z "$(git -C "$repo" status --porcelain)" ] || problem "the install left changes behind"

# Each committed command, run as Claude Code runs it.
entry() {
  python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["hooks"][sys.argv[2]][-1]["hooks"][0]["command"])' \
    "$repo/.claude/settings.json" "$1"
}
call() {
  printf '{"cwd": "%s", "session_id": "s", "tool_name": "Write", "tool_use_id": "%s"}' "$repo" "$1" |
    CLAUDE_PROJECT_DIR=$repo sh -c "$(entry PostToolUse)" 2> "$work/stderr"
}
echo 'def test_b(): pass' > "$repo/tests/test_b.py"
call t1
status=$?
[ "$status" -eq 0 ] || problem "the PostToolUse command exited $status: $(cat "$work/stderr")"
git -C "$repo" ls-tree -r --name-only refs/worktree/test-first/ledger 2> /dev/null |
  grep -qx tests/test_b.py || problem "the PostToolUse command recorded nothing"
# test_b passes with no code of its own: born green, which the Stop audit blocks on -- born
# in the first call's record, because the install recorded the worktree before it.
printf '{"cwd": "%s", "session_id": "s", "stop_hook_active": false}' "$repo" |
  CLAUDE_PROJECT_DIR=$repo sh -c "$(entry Stop)" 2> "$work/stderr"
status=$?
[ "$status" -eq 2 ] && grep -q "^born-green tests.test_b::test_b" "$work/stderr" ||
  problem "the Stop command exited $status: $(cat "$work/stderr")"

[ "$fail" -eq 0 ] && echo "ok: install-ledger"
exit "$fail"
