#!/usr/bin/env bash
# Runs the ledger and the audit end to end with a real test runner (pytest, through uv): scratch
# projects whose tool calls are recorded by scripts/python/ledger.py exactly as the PostToolUse
# hook records them, then `python3 scripts/python/audit.py` on the feature branch. The units in
# tests/python cover each rule against a stand-in runner; this checks the rules hold with
# pytest's own reports (quickstart step 4, spec Story 1, SC-001, SC-002, SC-004).
#
# Usage:  tests/audit.sh        from the repository root
set -uo pipefail

PRESET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LEDGER="$PRESET/scripts/python/ledger.py"
AUDIT="$PRESET/scripts/python/audit.py"
# The project's test command: pytest from uv's cache, one file per run, JUnit to {junit}.
RUN='uv run --quiet --no-project --with pytest python -m pytest -q -p no:cacheprovider --junitxml={junit} {file}'
fail=0
problem() {
  echo "FAIL: $*"
  fail=1
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# A project on a feature branch, with the ledger's configuration committed on main.
project() {
  local repo=$work/$1
  git init -q -b main "$repo"
  git -C "$repo" config user.email t@example.com
  git -C "$repo" config user.name T
  mkdir -p "$repo/tests" "$repo/src" "$repo/.specify"
  : > "$repo/src/__init__.py"
  printf 'def one():\n    return 1\n' > "$repo/src/base.py"
  printf 'from src.base import one\n\ndef test_base():\n    assert one() == 1\n' \
    > "$repo/tests/test_base.py"
  jq -n --arg run "$RUN" '{tests: ["tests/**"], sources: ["src/**"], run: $run}' \
    > "$repo/.specify/test-first.json"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m base
  git -C "$repo" checkout -q -b feat
  REPO=$repo
  CALLS=0
  record # the origin: nothing is born there
}

# Records one tool call, as the hook does after it.
record() {
  CALLS=$((CALLS + 1))
  printf '{"cwd": "%s", "session_id": "s", "tool_name": "Bash", "tool_use_id": "c%s"}' \
    "$REPO" "$CALLS" | python3 "$LEDGER" > /dev/null 2>&1
}

# write <path> <content>: one file of a call (several before one `record`).
write() {
  mkdir -p "$(dirname "$REPO/$1")"
  printf '%b' "$2" > "$REPO/$1"
}

# expect <exit status> <line...>: runs the audit and checks its status and report lines.
expect() {
  local status=$1 out code
  shift
  out=$(cd "$REPO" && python3 "$AUDIT" --deadline 120 2>&1)
  code=$?
  [ "$code" = "$status" ] || problem "$SCENARIO: exit $code, expected $status: $out"
  for line in "$@"; do
    grep -qE "^$line( |$)" <<< "$out" || problem "$SCENARIO: no line '$line' in: $out"
  done
}

TEST_B='from src.b import value\n\ndef test_b():\n    assert value() == 2\n'
CODE_B='def value():\n    return 2\n'
STUB_B='def value():\n    return None\n'

SCENARIO="test, then code (SC-002)"
project red
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
expect 0 "red tests.test_b::test_b"

SCENARIO="test and code in one call (SC-001)"
project with-code
write tests/test_b.py "$TEST_B" && write src/b.py "$CODE_B" && record
expect 1 "born-with-code tests.test_b::test_b"

SCENARIO="code, then test (SC-002)"
project green
write src/b.py "$CODE_B" && record
write tests/test_b.py "$TEST_B" && record
expect 1 "born-green tests.test_b::test_b"

SCENARIO="a file that cannot load, then a stub, then code"
project stub
write tests/test_b.py "$TEST_B" && record
write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
expect 0 "red tests.test_b::test_b"

SCENARIO="a red test rewritten in the call that adds its code (SC-002)"
project rewritten
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write tests/test_b.py 'from src.b import value\n\ndef test_b():\n    assert value() == 3\n'
write src/b.py 'def value():\n    return 3\n' && record
expect 1 "rewritten-to-green tests.test_b::test_b"

SCENARIO="tests renamed in a test-only call"
project refactored
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
write tests/test_b.py 'from src.b import value\n\ndef test_value_is_two():\n    assert value() == 2\n' && record
expect 0 "refactored tests.test_b::test_value_is_two" "  replaced tests.test_b::test_b"

SCENARIO="a moved test that passes at the base"
project predates
write tests/test_moved.py "$(cat "$REPO/tests/test_base.py")" && rm "$REPO/tests/test_base.py" && record
expect 0 "predates tests.test_moved::test_base"

SCENARIO="the redo sequence after a test born with its code"
project redo
write tests/test_b.py "$TEST_B" && write src/b.py "$CODE_B" && record
rm "$REPO/tests/test_b.py" "$REPO/src/b.py" && record
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
expect 0 "red tests.test_b::test_b"

SCENARIO="an xfail test is listed, not failing"
project xfail
write tests/test_b.py 'import pytest\n\n@pytest.mark.xfail(reason="later")\ndef test_b():\n    assert False\n' && record
expect 0 "never-run tests.test_b::test_b"

SCENARIO="a second audit reruns nothing"
memo=$(git -C "$REPO" rev-parse --path-format=absolute --git-path test-first/runs)
before=$(ls "$memo" | wc -l)
expect 0 "never-run tests.test_b::test_b"
[ "$(ls "$memo" | wc -l)" = "$before" ] || problem "$SCENARIO: the memo grew"

SCENARIO="a typo that breaks the file for one call, then fixed"
project typo
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write tests/test_b.py "$TEST_B)" && record
write tests/test_b.py "$TEST_B" && record
write src/b.py "$CODE_B" && record
expect 0 "red tests.test_b::test_b"

SCENARIO="git stash, then git stash pop in another call"
project stash
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
git -C "$REPO" add -A && git -C "$REPO" stash -q && record
git -C "$REPO" stash pop -q && record
expect 0 "red tests.test_b::test_b"

SCENARIO="a test written and committed in one call"
project committed
write tests/test_b.py "$TEST_B" && write src/b.py "$CODE_B"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "test and code" && record
expect 1 "unobserved tests.test_b::test_b"

SCENARIO="a replay that hangs"
project hang
write tests/test_b.py 'import time\n\ndef test_b():\n    time.sleep(600)\n' && record
out=$(cd "$REPO" && python3 "$AUDIT" --deadline 3 2>&1)
[ $? = 1 ] || problem "$SCENARIO: expected exit 1: $out"
# No run could say which tests the file holds, so the file itself stands unjudged.
grep -qE "^not-judged tests/test_b.py " <<< "$out" || problem "$SCENARIO: $out"
pgrep -f "time.sleep\(600\)|test_b.py" > /dev/null && problem "$SCENARIO: a replay is still running"

# Vitest reports a file that does not load differently from pytest (research L7): one failure
# case named after the file. A typo for one call must still not give the test a new birth.
if command -v pnpm > /dev/null && command -v node > /dev/null; then
  SCENARIO="Vitest: a typo that breaks the file for one call"
  vitest=$work/vitest-install
  mkdir -p "$vitest" && echo '{"private": true}' > "$vitest/package.json"
  if (cd "$vitest" && pnpm add -D vitest > /dev/null 2>&1); then
    RUN="$vitest/node_modules/.bin/vitest run {file} --globals --reporter=junit --outputFile={junit}"
    project vitest
    write tests/b.test.js 'import { value } from "../src/b.js";\ntest("b", () => expect(value()).toBe(2));\n'
    write src/b.js 'export const value = () => null;\n' && record
    write tests/b.test.js 'import { value } from "../src/b.js";\ntest("b", () => expect(value()).toBe(2)\n' && record
    write tests/b.test.js 'import { value } from "../src/b.js";\ntest("b", () => expect(value()).toBe(2));\n' && record
    write src/b.js 'export const value = () => 2;\n' && record
    expect 0 "red tests/b.test.js::b"
    RUN='uv run --quiet --no-project --with pytest python -m pytest -q -p no:cacheprovider --junitxml={junit} {file}'
  else
    echo "note: Vitest scenario skipped: pnpm could not install vitest"
  fi
else
  echo "note: Vitest scenario skipped: no node or pnpm on PATH"
fi

# SC-004: a feature of 60 new tests in 20 files, each file written red with a stub and then
# its code, audited from an empty memo and again with the memo warm. The cold figure is
# reported; the warm one must stay within 2 minutes.
SCENARIO="SC-004: 60 tests in 20 files"
project scale
for n in $(seq 1 20); do
  tests="from src.m$n import f\n"
  for k in 1 2 3; do tests+="\ndef test_${n}_$k():\n    assert f($k) == $((k * n))\n"; done
  write "tests/test_m$n.py" "$tests" && write "src/m$n.py" 'def f(k):\n    return None\n' && record
  write "src/m$n.py" "def f(k):\n    return k * $n\n" && record
done
for pass in cold warm; do
  start=$(date +%s)
  out=$(cd "$REPO" && python3 "$AUDIT" --deadline 120 2>&1)
  code=$?
  seconds=$(($(date +%s) - start))
  echo "SC-004 $pass audit: $seconds s, $(tail -1 <<< "$out")"
  [ "$code" = 0 ] || problem "$SCENARIO ($pass): exit $code: $(tail -3 <<< "$out")"
done
[ "$seconds" -le 120 ] || problem "$SCENARIO: the warm audit took $seconds s, over 2 minutes"

[ "$fail" -eq 0 ] && echo "ok: audit"
exit "$fail"
