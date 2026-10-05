# spec-kit-preset-test-first

A [Spec Kit](https://github.com/github/spec-kit) preset that makes test-first
the default instead of an opt-in. It appends to two core skills and replaces
nothing, so upstream changes to the rest of each skill keep arriving.

| Skill | What the preset adds |
|---|---|
| `speckit-tasks` | Test tasks are required (overriding core's "Tests are OPTIONAL") for behaviour with logic of its own; one behaviour per task; implementation tasks cite their `FR-`/`SC-` IDs |
| `speckit-implement` | A test counts once it has failed from inside, not on an import or collection error; a task is marked done only after a passing run |

## When to use it

- Work where a test that never failed is not evidence: domain logic, money,
  parsing, anything with edge cases.
- Projects that want every task traceable to a requirement ID.

## When not to use it

- Spikes and prototypes, where the point is to learn what to build.
- Features with no logic of their own (copy, styling, configuration): the
  preset exempts such tasks, but its one-behaviour-per-task granularity
  roughly doubled the task count in the pilot below, which buys nothing there.

Verified with the Claude Code integration only. The fragments are plain
Markdown and should compose for any integration that registers command
overrides, but that is not tested.

## Install

```bash
specify preset add --from https://github.com/camilopiedra92/spec-kit-preset-test-first/archive/refs/tags/v1.0.0.zip
```

To move a project to a newer release:
`specify preset update test-first --from <that tag's zip URL>`.

Once any preset is installed, Spec Kit's bash scripts resolve templates with
`python3` and PyYAML. If the `python3` on your PATH lacks PyYAML, point
`SPECKIT_PYTHON_EXECUTABLE` at one that has it — the specify CLI's own uv tool
environment does: `$(uv tool dir)/specify-cli/bin/python`.

## Verified

`tests/compose.sh` installs the preset from a tag-shaped archive into a scratch
project with the real CLI and checks that each skill keeps its core body and
description and ends with the fragment, and that core still carries the rule
the tasks fragment overrides. CI runs it against the pinned Spec Kit release on
every push and against the latest release weekly.

In one pilot (Spec Kit 1.1.0, 2026-10-05), `/speckit-tasks` produced 61 tasks,
52 citing requirement IDs, against 29 and 5 without the preset. Test tasks
appeared either way there, because the plan already carried a test strategy.
