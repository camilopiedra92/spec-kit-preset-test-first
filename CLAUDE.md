# spec-kit-preset-test-first

A Spec Kit preset that makes test-first the default: Markdown fragments appended
to the core `speckit-tasks` and `speckit-implement` skills, and the scripts they
run. Projects install it from a tag's archive (`README.md`, "Install"). This
repository is itself developed with Spec Kit, using the released version of
this preset.

## Commands

```bash
tests/compose.sh          # installs HEAD's archive with the real specify CLI; needs specify on PATH
tests/stop-gate.sh        # the 1.x Stop gate's installer and hook
tests/run-bounded.sh      # the deadline runner
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
                          # the Python scripts' lint, types and units (tests/python/)
tests/ledger.sh           # the PostToolUse hook end to end, and its cost per call (SC-003)
tests/audit.sh            # the audit and its Stop entry end to end with real pytest (SC-004)
tests/install-ledger.sh   # the installer end to end, and the hook commands it commits
```

CI (`.github/workflows/ci.yml`) runs all of them. `tests/compose.sh` tests what
is committed: commit before running it.

## Invariants

@.specify/memory/constitution.md

## Decisions

Before changing how the audit judges, which runners it supports, or how a Stop hook blocks, read
`docs/decisions/`: each record says what was considered and why it lost.

## Where things live

| Path | Holds |
|---|---|
| `commands/` | The fragments, one per core skill they append to |
| `scripts/bash/` | What the fragments run, installed under `.specify/presets/test-first/` |
| `scripts/python/` | The ledger hook, the audit and the installer, behind one entry point, `cli.py` |
| `docs/decisions/` | Decisions later changes must not reopen without saying so (MADR), export-ignored |
| `.specify/`, `.claude/`, `specs/` | This repository's own Spec Kit, export-ignored from the release |

---

When something here stops being true, correct it in the same commit that made
it false.
