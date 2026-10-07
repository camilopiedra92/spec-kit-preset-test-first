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
CLI="$PRESET/scripts/python/cli.py"
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
    "$REPO" "$CALLS" | python3 "$CLI" ledger > /dev/null 2>&1
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
  out=$(cd "$REPO" && python3 "$CLI" audit --deadline 120 2>&1)
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

SCENARIO="a file that cannot load, then the full code at once (scenario 5)"
project full-code
write tests/test_b.py "$TEST_B" && record
write src/b.py "$CODE_B" && record
expect 1 "born-with-code tests.test_b::test_b"

SCENARIO="red by an exception -- a missing method -- then the code (scenario 6)"
project exception
write src/b.py 'class B:\n    pass\n' && record
write tests/test_b.py 'from src.b import B\n\ndef test_b():\n    assert B().value() == 2\n' && record
write src/b.py 'class B:\n    def value(self):\n        return 2\n' && record
expect 0 "red tests.test_b::test_b"

SCENARIO="a red test edited until it passes in a test-only call (scenario 9)"
project edited
write src/b.py "$STUB_B" && record
write tests/test_b.py "$TEST_B" && record
write tests/test_b.py 'from src.b import value\n\ndef test_b():\n    assert value() is None\n' && record
expect 1 "rewritten-to-green tests.test_b::test_b"

SCENARIO="three accepted tests merged into one parametrized test (scenario 10)"
project consolidated
write tests/test_b.py 'from src.b import double\n\ndef test_one():\n    assert double(1) == 2\n\ndef test_two():\n    assert double(2) == 4\n\ndef test_three():\n    assert double(3) == 6\n'
write src/b.py 'def double(n):\n    return None\n' && record
write src/b.py 'def double(n):\n    return 2 * n\n' && record
write tests/test_b.py 'import pytest\nfrom src.b import double\n\n@pytest.mark.parametrize("n", [1, 2, 3])\ndef test_double(n):\n    assert double(n) == 2 * n\n' && record
expect 0 "refactored tests.test_b::test_double\[1\]" "refactored tests.test_b::test_double\[3\]"

SCENARIO="a rename beside one more passing test (scenario 10)"
project rename-plus
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
write tests/test_b.py 'from src.b import value\n\ndef test_renamed():\n    assert value() == 2\n\ndef test_extra():\n    assert value() > 1\n' && record
expect 1 "born-green tests.test_b::test_renamed" "born-green tests.test_b::test_extra"

SCENARIO="a red test turned green by a helper alone (scenario 11)"
project helper
write tests/helper.py 'EXPECTED = 3\n'
write tests/test_b.py 'from src.b import value\nfrom tests.helper import EXPECTED\n\ndef test_b():\n    assert value() == EXPECTED\n'
write tests/__init__.py '' && write src/b.py "$CODE_B" && record
write tests/helper.py 'EXPECTED = 2\n' && record
expect 1 "rewritten-to-green tests.test_b::test_b"

SCENARIO="behaviour first written outside the source globs (scenario 12)"
project template
write templates/greeting.txt 'hello\n' && record
write tests/test_b.py 'from pathlib import Path\n\ndef test_b():\n    assert Path("templates/greeting.txt").read_text() == "hello\\n"\n' && record
expect 1 "born-green tests.test_b::test_b"

SCENARIO="test, a commit in its own call, then code"
project commit-own-call
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "red test" && write NOTES.md 'committed\n' && record
write src/b.py "$CODE_B" && record
expect 0 "red tests.test_b::test_b"

SCENARIO="a test-helper refactor while every test is green"
project helper-refactor
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
write tests/conftest.py 'import pytest\n\n@pytest.fixture\ndef unused():\n    return 1\n' && record
expect 0 "red tests.test_b::test_b"

SCENARIO="an enum member renamed in code renames a parametrized id"
project enum
write src/colors.py 'COLORS = ["red"]\n\ndef known(c):\n    return False\n' && record
write tests/test_b.py 'import pytest\nfrom src.colors import COLORS, known\n\n@pytest.mark.parametrize("c", COLORS)\ndef test_c(c):\n    assert known(c)\n' && record
write src/colors.py 'COLORS = ["red"]\n\ndef known(c):\n    return c in COLORS\n' && record
write src/colors.py 'COLORS = ["crimson"]\n\ndef known(c):\n    return c in COLORS\n' && record
expect 0 "refactored tests.test_b::test_c\[crimson\]"

SCENARIO="a branch merged in brings its tests unobserved"
project merged
git -C "$REPO" checkout -q -b elsewhere main
write tests/test_b.py "$TEST_B" && write src/b.py "$CODE_B"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "written elsewhere"
git -C "$REPO" checkout -q feat && git -C "$REPO" merge -q --no-edit elsewhere && record
expect 1 "unobserved tests.test_b::test_b"

SCENARIO="a local merge into the default branch does not move the base"
project local-merge
git init -q --bare "$work/local-merge-origin.git"
git -C "$REPO" remote add origin "$work/local-merge-origin.git"
git -C "$REPO" push -q origin main && git -C "$REPO" fetch -q origin
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
git -C "$REPO" add -A && git -C "$REPO" commit -q -m feature
git -C "$REPO" checkout -q main && git -C "$REPO" merge -q --ff-only feat && git -C "$REPO" checkout -q feat
expect 0 "red tests.test_b::test_b"

SCENARIO="an API and its shared fixture changed in one call"
project shared-fixture
write tests/__init__.py '' && write src/v1.py 'def make():\n    return 1\n'
write tests/conftest.py 'import pytest\nfrom src.v1 import make\n\n@pytest.fixture\ndef thing():\n    return make()\n'
write tests/test_b.py 'from src.b import value\n\ndef test_b(thing):\n    assert value() == thing + 1\n'
write src/b.py "$STUB_B" && record
rm "$REPO/src/v1.py" && write src/v2.py 'def make():\n    return 1\n'
write tests/conftest.py 'import pytest\nfrom src.v2 import make\n\n@pytest.fixture\ndef thing():\n    return make()\n'
write src/b.py "$CODE_B" && record
expect 1 "not-judged tests.test_b::test_b"

SCENARIO="a test file left unloadable at the end"
project broken-end
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
write tests/test_b.py "$TEST_B)" && record
expect 1 "not-judged tests.test_b::test_b"

SCENARIO="a test rewritten together with the code for a new case"
project rewrite-new-case
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
write tests/test_b.py 'from src.b import value, more\n\ndef test_b_and_more():\n    assert (value(), more()) == (2, 3)\n'
write src/b.py "$CODE_B"'def more():\n    return 3\n' && record
expect 1 "born-with-code tests.test_b::test_b_and_more"

SCENARIO="a branch visit and a rebase onto newer main"
project visit-rebase
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
git -C "$REPO" add -A && git -C "$REPO" commit -q -m red && git -C "$REPO" checkout -q main
write OTHER.md 'on main\n' && git -C "$REPO" add -A && git -C "$REPO" commit -q -m "main moves" && record
git -C "$REPO" checkout -q feat && git -C "$REPO" rebase -q main && record
write src/b.py "$CODE_B" && record
expect 0 "red tests.test_b::test_b"

SCENARIO="an environment that imports the real worktree's code cannot make a test predate"
project editable
RUN_SAVED=$RUN
jq --arg run 'PYTHONPATH={root} uv run --quiet --no-project --with pytest python -m pytest -q -p no:cacheprovider --import-mode=append --junitxml={junit} {file}' '.run = $run' "$REPO/.specify/test-first.json" > "$work/editable.json"
cp "$work/editable.json" "$REPO/.specify/test-first.json"
git -C "$REPO" add -A && git -C "$REPO" commit -q -m "run through the real worktree"
write src/b.py "$CODE_B" && record
write tests/test_b.py "$TEST_B" && record
expect 1 "born-green tests.test_b::test_b"
RUN=$RUN_SAVED

SCENARIO="an audit killed mid-run leaves no scratch worktree behind the next one"
project killed
write tests/test_slow.py 'import time\n\ndef test_slow():\n    time.sleep(60)\n' && record
(cd "$REPO" && exec python3 "$CLI" audit --deadline 120) > /dev/null 2>&1 &
audit_pid=$!
for _ in $(seq 1 50); do
  [ "$(git -C "$REPO" worktree list | wc -l | tr -d ' ')" -gt 1 ] && break
  sleep 0.2
done
kill -9 "$audit_pid" 2> /dev/null
wait "$audit_pid" 2> /dev/null
pkill -f "time.sleep\(60\)" 2> /dev/null
rm "$REPO/tests/test_slow.py" && record
write tests/test_b.py "$TEST_B" && write src/b.py "$STUB_B" && record
write src/b.py "$CODE_B" && record
expect 0 "red tests.test_b::test_b"
[ "$(git -C "$REPO" worktree list | wc -l | tr -d ' ')" = 1 ] ||
  problem "$SCENARIO: worktrees left: $(git -C "$REPO" worktree list)"

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
# The test writes its process id where this script can see it: whether the replay survived
# the deadline is then a fact, not a guess from command lines.
write tests/test_b.py "import os, time\n\ndef test_b():\n    open('$work/hang.pid', 'w').write(str(os.getpid()))\n    time.sleep(600)\n" && record
out=$(cd "$REPO" && python3 "$CLI" audit --deadline 3 2>&1)
[ $? = 1 ] || problem "$SCENARIO: expected exit 1: $out"
# No run could say which tests the file holds, so the file itself stands unjudged.
grep -qE "^not-judged tests/test_b.py " <<< "$out" || problem "$SCENARIO: $out"
# A killed process can take a moment to go; one still there after two seconds survived.
survivor=
if [ -s "$work/hang.pid" ]; then
  survivor=$(cat "$work/hang.pid")
  for _ in $(seq 1 10); do
    kill -0 "$survivor" 2> /dev/null || { survivor=; break; }
    sleep 0.2
  done
else
  problem "$SCENARIO: the hanging test never started"
fi
[ -z "$survivor" ] || { kill -9 "$survivor"; problem "$SCENARIO: a replay is still running"; }

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

# The Stop hook (FR-024): one turn's test and code written together blocks the turn once, within
# SC-004's 30 seconds; the next stop of that turn goes through.
SCENARIO="the Stop hook blocks once on a test born with its code"
project stop
write tests/test_b.py "$TEST_B" && write src/b.py "$CODE_B" && record
start=$(date +%s)
out=$(printf '{"cwd": "%s", "session_id": "s", "stop_hook_active": false}' "$REPO" |
  python3 "$CLI" audit --stop 2>&1)
code=$?
seconds=$(($(date +%s) - start))
echo "SC-004 Stop audit of one turn: $seconds s"
[ "$code" = 2 ] && grep -q "^born-with-code tests.test_b::test_b " <<< "$out" ||
  problem "$SCENARIO: exit $code: $out"
[ "$seconds" -le 30 ] || problem "$SCENARIO: $seconds s, over 30"
printf '{"cwd": "%s", "session_id": "s", "stop_hook_active": true}' "$REPO" |
  python3 "$CLI" audit --stop > /dev/null 2>&1 || problem "$SCENARIO: the next stop was blocked"

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
  out=$(cd "$REPO" && python3 "$CLI" audit --deadline 120 2>&1)
  code=$?
  seconds=$(($(date +%s) - start))
  echo "SC-004 $pass audit: $seconds s, $(tail -1 <<< "$out")"
  [ "$code" = 0 ] || problem "$SCENARIO ($pass): exit $code: $(tail -3 <<< "$out")"
done
[ "$seconds" -le 120 ] || problem "$SCENARIO: the warm audit took $seconds s, over 2 minutes"

[ "$fail" -eq 0 ] && echo "ok: audit"
exit "$fail"
