# spec-kit-preset-test-first

A Spec Kit preset that makes test-first the default: Markdown fragments appended
to the core `speckit-tasks` and `speckit-implement` skills, and the scripts they
run. Projects install it from a tag's archive (`README.md`, "Install"). This
repository is itself developed with Spec Kit, using the released version of
this preset.

## Commands

```bash
tests/compose.sh       # installs HEAD's archive with the real specify CLI; needs specify on PATH
tests/stop-gate.sh     # the Stop gate's installer and hook
tests/run-bounded.sh   # the deadline runner
```

CI (`.github/workflows/ci.yml`) runs all three. `tests/compose.sh` tests what
is committed: commit before running it.

## Invariants

@.specify/memory/constitution.md

## Where things live

| Path | Holds |
|---|---|
| `commands/` | The fragments, one per core skill they append to |
| `scripts/bash/` | What the fragments run, installed under `.specify/presets/test-first/` |
| `.specify/`, `.claude/`, `specs/` | This repository's own Spec Kit, export-ignored from the release |

---

When something here stops being true, correct it in the same commit that made
it false.
