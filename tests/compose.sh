#!/usr/bin/env bash
# Installs this preset into a scratch Spec Kit project with the real CLI and
# checks what it does to the two skills it appends to. The CLI version is
# whatever `specify` is on PATH: CI runs it pinned and against the latest
# release, which is how an upstream change to the core skills shows up here
# before it shows up in a project.
#
# Usage:  tests/compose.sh        from the repository root
set -euo pipefail

PRESET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work=$(mktemp -d)
server=
trap '[ -n "$server" ] && kill "$server" 2> /dev/null; rm -rf "$work"' EXIT
# Quiet on success, the whole output on failure: the CLI reports through a
# rich console on stdout, so silencing it blindly hid why CI failed.
quiet() {
  "$@" > "$work/last.log" 2>&1 || {
    echo "FAIL: $*"
    cat "$work/last.log"
    exit 1
  }
}

# Installed the way a project installs it: GitHub's tag archive is a zip of the
# committed tree under one top-level directory, minus export-ignore paths, and
# `--from` downloads it. git archive builds the same shape from HEAD, and the
# CLI accepts plain HTTP from localhost only, so a local server stands in for
# GitHub. Uncommitted changes are not in HEAD and so are not tested.
mkdir "$work/www"
quiet git -C "$PRESET" archive --format=zip --prefix=spec-kit-preset-test-first/ \
  -o "$work/www/preset.zip" HEAD
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
python3 -m http.server "$port" --bind 127.0.0.1 --directory "$work/www" > /dev/null 2>&1 &
server=$!
disown "$server"
for _ in $(seq 50); do
  curl -sf -o /dev/null "http://127.0.0.1:$port/preset.zip" && break
  sleep 0.1
done
fail=0
problem() {
  echo "FAIL: $*"
  fail=1
}

# The specify CLI's own environment ships PyYAML; the system python3 may not.
PY="${SPECKIT_PYTHON_EXECUTABLE:-$(uv tool dir)/specify-cli/bin/python}"
description() {
  "$PY" -c 'import sys, yaml
text = open(sys.argv[1], encoding="utf-8").read()
print(yaml.safe_load(text.split("---")[1])["description"])' "$1"
}

cd "$work"
quiet git init -q
# The skills are what is under test, not Claude Code, which a runner lacks:
# without this, init stops at "claude not found".
quiet specify init --here --force --integration claude --ignore-agent-tools
skills=.claude/skills
mkdir core
for s in tasks implement; do cp "$skills/speckit-$s/SKILL.md" "core/$s.md"; done

# The tasks fragment says it replaces this rule. If upstream drops or rewords
# it, the fragment refers to nothing and has to be revised.
grep -q 'Tests are OPTIONAL' core/tasks.md ||
  problem "core speckit-tasks no longer says 'Tests are OPTIONAL'; revise the fragment"
grep -qF 'Tests (if requested) → Models' core/tasks.md ||
  problem "core speckit-tasks no longer orders 'Tests (if requested) → Models'; revise the fragment"
grep -qF 'Write these tests FIRST' .specify/templates/tasks-template.md ||
  problem "core tasks-template.md no longer has its 'Write these tests FIRST' block; revise the fragment"
# Same for the implement step the fragment narrows by name.
grep -q 'Project Setup Verification' core/implement.md ||
  problem "core speckit-implement no longer has 'Project Setup Verification'; revise the fragment"

quiet specify preset add --from "http://127.0.0.1:$port/preset.zip"

for s in tasks implement; do
  skill="$skills/speckit-$s/SKILL.md"
  fragment="$PRESET/commands/speckit.$s.md"
  # Appended: the core body survives and the fragment closes the file.
  body_start=$(awk '/^---$/{n++; next} n>=2' "core/$s.md" | grep -m1 -v '^\s*$')
  grep -qF -- "$body_start" "$skill" || problem "speckit-$s lost the core body"
  [ "$(tail -n "$(wc -l < "$fragment")" "$skill")" = "$(cat "$fragment")" ] ||
    problem "speckit-$s does not end with the fragment"
  # The description is what Claude reads to decide when to invoke the skill;
  # a fragment with frontmatter replaces it.
  # Compared as parsed YAML, because the CLI re-serializes the frontmatter
  # (quotes dropped, long lines folded) whenever it composes a skill.
  [ "$(description "$skill")" = "$(description "core/$s.md")" ] ||
    problem "speckit-$s description changed: $(description "$skill")"
done

# The implement fragment runs the installer by this path, so it must land
# there as committed. Through `bash`, because installing from an archive drops
# the executable bit (specify 1.1.0: 644 from a zip that stores 755).
gate=.specify/presets/test-first/scripts/bash/install-stop-gate.sh
cmp -s "$gate" "$PRESET/scripts/bash/install-stop-gate.sh" ||
  problem "$gate is not installed as committed"
grep -qF "bash $gate" "$skills/speckit-implement/SKILL.md" ||
  problem "speckit-implement does not run bash $gate"

specify version > version.txt 2>&1 || true
[ "$fail" -eq 0 ] && echo "ok: composes on specify $(grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+' version.txt)"
exit "$fail"
