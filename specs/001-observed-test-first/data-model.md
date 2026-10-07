# Data Model: Observed test-first

## Configuration — `.specify/test-first.json` (committed)

| Field | Type | Rule |
|---|---|---|
| `tests` | list of globs | Non-empty; matches at least one tracked file at install (FR-014) |
| `sources` | list of globs | Non-empty; a path matching both `tests` and `sources` counts as a test |
| `run` | string | Contains `{files}` and `{junit}`; may contain `{root}` |

Glob semantics: `fnmatch` on the repository-relative POSIX path, where `**` matches across
directories (`tests/**` matches `tests/a/b.py`). A path matching neither list is neither test nor
source (documentation, `tasks.md`, configuration).

## Record (a commit in the ledger)

| Field | Where | Rule |
|---|---|---|
| tree | the commit's tree | the worktree's tracked and untracked-but-not-ignored files after the call |
| previous | the commit's single parent | absent only for the first record of a worktree |
| `time` | message JSON | ISO 8601 UTC, when the hook ran |
| `session` | message JSON | `session_id` from the hook input |
| `agent` | message JSON | `agent_id` from the hook input, `null` for the main conversation |
| `tool` | message JSON | `tool_name` |
| `call` | message JSON | `tool_use_id` |

Invariants: a record's tree differs from its parent's (FR-002); records are only ever appended.

## Ledger

The chain reachable from `refs/worktree/test-first/ledger` in one worktree, oldest first when read.
The audit's range is the records whose `time` is after the base commit's committer time.

## Change (derived, not stored)

For a record: the paths that differ from its parent's tree, split into test paths, source paths and
other paths by the configuration. A change is **mixed** when it has both test and source paths.

## Test outcome (from one JUnit XML)

`id` = `classname` + "::" + `name`; `outcome` ∈ {`failed`, `error`, `skipped`, `passed`}: a
`testcase` with a `failure` child is failed, with an `error` child error, with a `skipped` child
skipped, otherwise passed. A file that produces no JUnit (the command crashed) gives every test
previously known in that file the outcome `error`.

## Birth

For a new test: the first record of the last contiguous stretch of records at which the test exists
in its file's JUnit. Presence is re-evaluated only at records whose change touched that test file,
so a test's existence between them is carried forward.

## Verdict

| Verdict | Condition | Fails the audit |
|---|---|---|
| `red` | first non-error outcome from birth on is `failed` | no |
| `predates` | outcome at birth `passed`, and its birth file passes it against the base's sources | no |
| `born-with-code` | outcome at birth `passed`, not `predates`, and the birth change is mixed | yes |
| `born-green` | outcome at birth `passed`, not `predates`, and the birth change is test-only | yes |
| `unobserved` | new at the end of the range, but present in no record of the range | yes |
| `never-run` | only `error` or `skipped` from birth to the end of the range | yes |
| `not-judged` | a replay it depends on exceeded its deadline | yes |

New test = present in the end state's JUnit for the test files that changed in the range, absent
from the base's JUnit for the same files.
