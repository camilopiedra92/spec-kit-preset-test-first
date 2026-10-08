"""The preset's entry point: `python3 cli.py ledger` (the PostToolUse hook),
`python3 cli.py audit [options]` (the audit, and its Stop hook) or
`python3 cli.py install [options]` (the installer).

Claude Code runs it with whatever python3 a project has on its PATH, which may be older than
the scripts support -- the macOS one is 3.9. So this file stays parseable by any Python 3 and
checks the version before importing anything else; the modules it dispatches to are free to
use the supported version's standard library. tests/ledger.sh runs it under a real 3.9.
"""

import sys

# The oldest CPython still supported (3.10 reached its end of life on 2026-10-01), and Spec
# Kit's own floor.
FLOOR = (3, 11)


def main() -> int:
    if sys.version_info < FLOOR:
        if sys.argv[1:3] == ["audit", "--stop"] and _continued_stop():
            return 0  # one block per turn, as the Stop hook itself does
        found = ".".join(map(str, sys.version_info[:3]))
        # Exit 2: Claude Code shows a hook's stderr to Claude only on that status.
        print(f"test-first: needs python3 >= {FLOOR[0]}.{FLOOR[1]}, found {found}", file=sys.stderr)
        return 2
    # The modules live in the project's tree (.specify/presets/...): bytecode cached beside them
    # would be an untracked __pycache__ in the project after every hook call.
    sys.dont_write_bytecode = True
    command, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if command == "ledger":
        import ledger

        return ledger.main()
    if command == "audit":
        import audit

        return audit.main(args)
    if command == "install":
        import install

        return install.main(args)
    print(
        "usage: cli.py ledger | cli.py audit [options] | cli.py install [options]", file=sys.stderr
    )
    return 2


def _continued_stop() -> bool:
    """Whether the Stop payload says a Stop hook already blocked this turn. Read with the
    oldest Python 3's json, before the version check exits."""
    import json

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("stop_hook_active") is True


if __name__ == "__main__":
    sys.exit(main())
