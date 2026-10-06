#!/usr/bin/env bash
# Tests scripts/bash/install-stop-gate.sh against a fake suite whose verdict a
# file sets, which logs each run with its arguments and its directory, and
# which stages a file when told to. Under test: what the installer refuses,
# that a refused or failed run leaves nothing behind, what lands in its
# commit, and what the Stop hook it writes does on each kind of stop -- exit 2
# with the failure on stderr is what makes Claude Code block and show it; any
# other code lets the stop through.
#
# Moved here with the installer from github.com/camilopiedra92/dotfiles
# (check.sh, sdd_gate), where it was the sdd-gate command.
#
# Usage:  tests/stop-gate.sh        from the repository root
set -uo pipefail

PRESET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

stop_gate() {
  local tmp repo out rc
  tmp=$(mktemp -d) || return 1
  trap 'rm -rf "$tmp"' RETURN
  mkdir -p "$tmp/bin"
  cat > "$tmp/bin/suite" << FAKE
#!/bin/sh
printf '%s|' "\$@" >> "$tmp/runs"
echo >> "$tmp/runs"
pwd -P > "$tmp/cwd"
[ ! -e "$tmp/stage" ] || { echo x > snapshot.txt; git add snapshot.txt; }
if [ "\$(cat "$tmp/verdict")" = escape ]; then
  # A child that leaves the suite's process group, still holding its output.
  perl -MPOSIX -e 'fork and exit; POSIX::setsid(); sleep 9302'
fi
case "\$(cat "$tmp/verdict")" in hang | escape) exec sleep 9301 ;; esac
echo "suite says \$(cat "$tmp/verdict")"
[ "\$(cat "$tmp/verdict")" = green ]
FAKE
  chmod +x "$tmp/bin/suite"
  ln -s "$PRESET/scripts/bash/install-stop-gate.sh" "$tmp/install-stop-gate"
  # A repository with a committed settings.json, or with no .claude/ at all,
  # and with the preset's runner where an installed preset puts it.
  runner=.specify/presets/test-first/scripts/bash/run-bounded.sh
  fresh() {
    repo="$tmp/repo-$1"
    git init -q "$repo"
    mkdir -p "$repo/$(dirname "$runner")"
    cp "$PRESET/scripts/bash/run-bounded.sh" "$repo/$runner"
    git -C "$repo" add "$runner"
    if [ "${2:-}" != bare ]; then
      mkdir -p "$repo/.claude"
      echo '{"permissions": {"deny": ["Read(./.env)"]}}' > "$repo/.claude/settings.json"
      git -C "$repo" add .claude/settings.json
    fi
    git -C "$repo" -c user.name=t -c user.email=t@t commit -q --allow-empty -m root
    echo green > "$tmp/verdict"
    rm -f "$tmp/stage"
    : > "$tmp/runs"
  }
  # Arguments a shell would rewrite if the hook quoted them carelessly: a
  # space, a single quote, a leading tilde, a tilde after `=` (zsh leaves that
  # one alone).
  run() {
    (cd "$repo" && GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t \
      GIT_COMMITTER_EMAIL=t@t ../install-stop-gate "$tmp/bin/suite" "two words" "it's" '~' 'a=~/x' 2>&1)
  }
  # A refused or failed run must leave .claude/ and the status as they were.
  snapshot() {
    (cd "$repo" && git status --porcelain --ignored && find .claude -print 2> /dev/null | sort &&
      cat .claude/settings.json 2> /dev/null)
  }
  # The hook as Claude Code calls it: event JSON on stdin, project dir in env,
  # started from somewhere else. Leaves rc and the two streams in files.
  stop() {
    (cd / && CLAUDE_PROJECT_DIR=$repo "$repo/.claude/hooks/stop-gate.sh" \
      <<< "{\"hook_event_name\":\"Stop\",\"stop_hook_active\":$1}") \
      > "$tmp/stdout" 2> "$tmp/stderr"
    rc=$?
  }

  # A gate over a red suite would block every turn, so it refuses one.
  fresh red
  echo red > "$tmp/verdict"
  local before
  before=$(snapshot)
  if out=$(run); then
    echo "gated a red suite: $out"
    return 1
  fi
  [ "$(snapshot)" = "$before" ] || {
    echo "refusing a red suite left something behind"
    return 1
  }

  # The hook runs the suite through the runner, so without it the gate could
  # not keep its deadline; refused before anything is written. Committed, or
  # every other clone would get a gate whose runner is missing.
  fresh no-runner
  git -C "$repo" rm -q "$runner"
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m "no runner"
  before=$(snapshot)
  if out=$(run); then
    echo "installed a gate with no runner: $out"
    return 1
  fi
  [ "$(snapshot)" = "$before" ] || {
    echo "refusing for a missing runner left something behind"
    return 1
  }
  fresh untracked-runner
  git -C "$repo" rm -q --cached "$runner"
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m "runner untracked"
  if out=$(run); then
    echo "installed a gate whose runner git does not track: $out"
    return 1
  fi

  # The happy path: one commit with the hook and the settings, keeping what
  # the settings already held, and nothing else -- not an untracked file, an
  # unstaged edit, or what the suite itself staged.
  fresh ok
  echo old > "$repo/tracked.txt"
  git -C "$repo" add tracked.txt
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m tracked
  echo new > "$repo/tracked.txt"
  echo x > "$repo/notes.txt"
  : > "$tmp/stage"
  out=$(run) || {
    echo "refused a green suite: $out"
    return 1
  }
  rm -f "$tmp/stage"
  [ "$(git -C "$repo" diff-tree --no-commit-id --name-only -r HEAD | sort | tr '\n' ' ')" = \
    ".claude/hooks/stop-gate.sh .claude/settings.json " ] || {
    echo "the commit holds something else:"
    git -C "$repo" show --stat HEAD
    return 1
  }
  jq -e '.permissions.deny == ["Read(./.env)"] and
    (.hooks.Stop | length) == 1 and
    .hooks.Stop[0].hooks[0].command == "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stop-gate.sh" and
    .hooks.Stop[0].hooks[0].timeout == 600' \
    "$repo/.claude/settings.json" > /dev/null || {
    echo "settings.json is not the old one plus one Stop hook:"
    cat "$repo/.claude/settings.json"
    return 1
  }

  # The deadline and the runner's 5-second grace fit inside the timeout
  # Claude Code gives the hook, or it would be stopped first.
  deadline=$(sed -n 's/^DEADLINE=//p' "$repo/.claude/hooks/stop-gate.sh")
  hook_timeout=$(jq '.hooks.Stop[0].hooks[0].timeout' "$repo/.claude/settings.json")
  [ -n "$deadline" ] && [ $((deadline + 5)) -lt "$hook_timeout" ] || {
    echo "DEADLINE=$deadline plus the grace does not fit the hook's timeout of $hook_timeout"
    return 1
  }

  # The commit names the command as a shell reads it back, quotes included,
  # not as its words run together.
  # shellcheck disable=SC2016  # the expected text, not an expansion
  git -C "$repo" log -1 --format=%B | grep -qF "runs \`'$tmp/bin/suite' 'two words' 'it'\\''s' '~' 'a=~/x'\`" || {
    echo "the gate's commit does not quote the command: $(git -C "$repo" log -1 --format=%B)"
    return 1
  }

  # How to turn it off is said where someone who wants to will look: the
  # hook and its commit. Deleting the hook instead would bring it back.
  off="remove its entry under hooks.Stop in .claude/settings.json and keep"
  tr -s ' #\n' '   ' < "$repo/.claude/hooks/stop-gate.sh" | grep -qF "$off" || {
    echo "the hook does not say how to turn it off"
    return 1
  }
  git -C "$repo" log -1 --format=%B | tr -s ' \n' '  ' | grep -qF "$off" || {
    echo "the gate's commit does not say how to turn it off: $(git -C "$repo" log -1 --format=%B)"
    return 1
  }

  # Green: the stop goes through, and the suite ran once, from the project,
  # with its arguments exactly as given.
  : > "$tmp/runs"
  stop false
  [ "$rc" -eq 0 ] || {
    echo "blocked a green stop (rc $rc): $(cat "$tmp/stderr")"
    return 1
  }
  [ "$(cat "$tmp/runs")" = "two words|it's|~|a=~/x|" ] || {
    echo "the suite did not run once with its arguments as given: $(cat "$tmp/runs")"
    return 1
  }
  [ "$(cat "$tmp/cwd")" = "$(cd "$repo" && pwd -P)" ] || {
    echo "the suite ran in $(cat "$tmp/cwd"), not the project"
    return 1
  }
  # Red: exit 2, the suite's output on stderr, even though nothing changed
  # since the green run. Every stop runs the suite.
  echo red > "$tmp/verdict"
  stop false
  [ "$rc" -eq 2 ] || {
    echo "a red stop exited $rc, which Claude Code does not treat as a block"
    return 1
  }
  grep -q "suite says red" "$tmp/stderr" || {
    echo "the failure is not on stderr, where Claude Code shows it: $(cat "$tmp/stdout")"
    return 1
  }
  # The second stop of the same turn goes through without running anything:
  # Claude has seen the failure and reports it rather than forcing it green.
  : > "$tmp/runs"
  stop true
  [ "$rc" -eq 0 ] && [ ! -s "$tmp/runs" ] || {
    echo "the second stop of a turn was blocked or ran the suite (rc $rc)"
    return 1
  }

  # A suite that never finishes is stopped at the hook's deadline, its whole
  # process group with it, and the turn is blocked saying so. The deadline is
  # a line of the hook, as the command is; shortened here.
  sed -i.bak 's/^DEADLINE=.*/DEADLINE=1/' "$repo/.claude/hooks/stop-gate.sh"
  rm -f "$repo/.claude/hooks/stop-gate.sh.bak"
  echo hang > "$tmp/verdict"
  local start=$SECONDS
  stop false
  if ! { [ "$rc" -eq 2 ] && grep -qF "did not finish in 1s" "$tmp/stderr"; }; then
    echo "a hung suite did not block the stop with its deadline (rc $rc): $(cat "$tmp/stderr")"
    return 1
  fi
  [ $((SECONDS - start)) -le 4 ] || {
    echo "a hung suite held the stop for $((SECONDS - start))s on a 1s deadline"
    return 1
  }
  if pgrep -f "^sleep 9301" > /dev/null; then
    pkill -KILL -f "sleep 9301"
    echo "the hung suite outlived the hook"
    return 1
  fi

  # A process that left the suite's group keeps running, but it does not hold
  # the stop past the deadline.
  echo escape > "$tmp/verdict"
  start=$SECONDS
  stop false
  pkill -KILL -f "sleep 930[12]"
  [ "$rc" -eq 2 ] || {
    echo "a suite with an escaped child did not block the stop (rc $rc)"
    return 1
  }
  [ $((SECONDS - start)) -le 4 ] || {
    echo "an escaped child held the stop for $((SECONDS - start))s on a 1s deadline"
    return 1
  }

  # Without the runner the gate blocks, naming it, instead of letting the turn
  # through unchecked, and does not send Claude to fix code that is not wrong.
  echo green > "$tmp/verdict"
  mv "$repo/$runner" "$tmp/runner"
  stop false
  mv "$tmp/runner" "$repo/$runner"
  if ! { [ "$rc" -eq 2 ] && grep -qF "run-bounded.sh" "$tmp/stderr" &&
    ! grep -qF "is red" "$tmp/stderr"; }; then
    echo "a missing runner did not block the stop with its name (rc $rc): $(cat "$tmp/stderr")"
    return 1
  fi

  # A second run would add a second hook. Green, so only that can refuse it.
  echo green > "$tmp/verdict"
  if out=$(run); then
    echo "ran again over an existing gate: $out"
    return 1
  fi
  # Nothing is written through a symlink, at the hook's path or the settings'.
  fresh symlink
  mkdir -p "$repo/.claude/hooks"
  ln -s "$tmp/elsewhere" "$repo/.claude/hooks/stop-gate.sh"
  if out=$(run); then
    echo "wrote the hook through a dangling symlink: $out"
    return 1
  fi
  fresh linked-settings bare
  echo '{}' > "$tmp/shared.json"
  mkdir -p "$repo/.claude"
  ln -s "$tmp/shared.json" "$repo/.claude/settings.json"
  git -C "$repo" add .claude/settings.json
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m link
  if out=$(run); then
    echo "wrote settings.json through a symlink: $out"
    return 1
  fi
  [ "$(cat "$tmp/shared.json")" = '{}' ] || {
    echo "changed the file a symlinked settings.json points to"
    return 1
  }

  # Anything uncommitted in what it commits would ride along: staged work, an
  # unstaged or untracked settings.json, or one git is told not to look at.
  fresh staged
  echo x > "$repo/notes.txt"
  git -C "$repo" add notes.txt
  if out=$(run); then
    echo "accepted a repo with staged changes: $out"
    return 1
  fi
  fresh unstaged
  echo '{"permissions": {"allow": ["Bash(curl:*)"]}}' > "$repo/.claude/settings.json"
  if out=$(run); then
    echo "committed an unstaged settings.json edit: $out"
    return 1
  fi
  fresh untracked bare
  mkdir -p "$repo/.claude"
  echo '{"permissions": {"allow": ["Bash(curl:*)"]}}' > "$repo/.claude/settings.json"
  if out=$(run); then
    echo "committed an untracked settings.json: $out"
    return 1
  fi
  for flag in --assume-unchanged --skip-worktree; do
    fresh "flag$flag"
    git -C "$repo" update-index "$flag" .claude/settings.json
    if out=$(run); then
      echo "accepted a settings.json marked $flag: $out"
      return 1
    fi
    echo "$out" | grep -q "is marked" || {
      echo "refused a settings.json marked $flag for another reason: $out"
      return 1
    }
  done

  # A settings.json that is not a JSON object stops it before anything is
  # written, and once fixed a re-run works.
  for bad in '{not json' '' '[]'; do
    fresh "bad-settings"
    printf '%s' "$bad" > "$repo/.claude/settings.json"
    git -C "$repo" -c user.name=t -c user.email=t@t commit -q -am "bad settings"
    before=$(snapshot)
    if out=$(run); then
      echo "accepted a settings.json of '$bad': $out"
      return 1
    fi
    [ "$(snapshot)" = "$before" ] || {
      echo "refusing a settings.json of '$bad' left something behind"
      return 1
    }
  done
  echo '{}' > "$repo/.claude/settings.json"
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -am "fix settings"
  out=$(run) || {
    echo "refused a re-run after the cause was fixed: $out"
    return 1
  }

  # An ignored .claude/ is refused up front, for that reason.
  fresh ignored
  echo .claude/ > "$repo/.gitignore"
  git -C "$repo" add .gitignore
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m "ignore .claude"
  if out=$(run); then
    echo "gated a repo that ignores .claude/: $out"
    return 1
  fi
  echo "$out" | grep -q "ignored" || {
    echo "refused an ignored .claude/ for another reason: $out"
    return 1
  }

  # A failure at the commit itself puts everything back -- a repository with
  # no .claude/, and one whose .claude/ already held files and an empty hooks/
  # directory -- and a re-run then works.
  for kind in bare full; do
    if [ "$kind" = bare ]; then fresh rollback bare; else
      fresh rollback-full
      mkdir -p "$repo/.claude/agents" "$repo/.claude/hooks"
      echo x > "$repo/.claude/agents/x.md"
    fi
    mkdir -p "$repo/.git/hooks"
    printf '#!/bin/sh\nexit 1\n' > "$repo/.git/hooks/pre-commit"
    chmod +x "$repo/.git/hooks/pre-commit"
    before=$(snapshot)
    if out=$(run); then
      echo "reported success when the commit was refused: $out"
      return 1
    fi
    # Said in its own words: a commit hook's output alone does not say that
    # the gate is what it refused.
    echo "$out" | grep -q "install-stop-gate: the commit was refused" || {
      echo "a refused commit did not say so: $out"
      return 1
    }
    [ "$(snapshot)" = "$before" ] || {
      echo "a refused commit in a $kind repository left it changed:"
      diff <(echo "$before") <(snapshot)
      return 1
    }
    rm "$repo/.git/hooks/pre-commit"
    out=$(run) || {
      echo "refused a re-run after a failed commit: $out"
      return 1
    }
  done

  # Reverting the feature that installed the gate removes both its files.
  # That is not a decision about the gate, so the next run installs it again,
  # whatever else was deleted before it.
  fresh reverted
  echo x > "$repo/old.txt"
  git -C "$repo" add old.txt
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m "old file"
  git -C "$repo" rm -q old.txt
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -m "drop old file"
  out=$(run) || {
    echo "refused a first install: $out"
    return 1
  }
  git -C "$repo" -c user.name=t -c user.email=t@t revert --no-edit HEAD > /dev/null
  out=$(run) || {
    echo "refused to reinstall after the gate's commit was reverted: $out"
    return 1
  }

  # Opting out is removing the Stop entry and keeping the hook: its presence
  # is what /speckit-implement checks, so the installer refuses from then on.
  fresh optout
  out=$(run) || {
    echo "refused a first install: $out"
    return 1
  }
  echo '{"permissions": {"deny": ["Read(./.env)"]}}' > "$repo/.claude/settings.json"
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -am "turn the gate off"
  if out=$(run); then
    echo "reinstalled a gate the repository turned off: $out"
    return 1
  fi

  # A Stop entry already pointing at the hook means a second would be added.
  fresh half-removed
  # shellcheck disable=SC2016  # the literal Claude Code expands, as the installer writes it
  echo '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stop-gate.sh"}]}]}}' \
    > "$repo/.claude/settings.json"
  git -C "$repo" -c user.name=t -c user.email=t@t commit -q -am "entry without hook"
  if out=$(run); then
    echo "added a second Stop entry for the gate: $out"
    return 1
  fi
  echo "$out" | grep -q "already has a Stop entry" || {
    echo "refused a leftover Stop entry for another reason: $out"
    return 1
  }
}

if stop_gate; then
  echo "ok: install-stop-gate"
else
  echo "FAIL: install-stop-gate"
  exit 1
fi
