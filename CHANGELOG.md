# Changelog

All notable changes to this preset are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.5.1] - 2026-10-06

### Fixed

- Story review: each run of a wrong version goes through
  `scripts/bash/run-bounded.sh <seconds> <command>`, which runs the command
  in a process group of its own and kills the whole group when the command
  ends, when the deadline passes (SIGTERM, then SIGKILL after 5 seconds), or
  when the runner itself gets TERM, INT, HUP or QUIT, repeating the kill
  until no member is left (up to 20 times). Exit 124 says the deadline
  fired, whatever the command answered; a deadline other than 1 to
  999999999 written plainly is refused with exit 2, since one `sleep` rejects
  would fire at once and read as caught. A wrong version
  that looped in the CLI under test ran for 13 hours after its review ended,
  to 232 GB of virtual memory and 67 GB of swap: the Bash tool's timeout
  moved the run to the background instead of stopping it, and the
  reviewer's `subprocess.run(timeout=...)` and `pkill` each stopped one
  process, not its children. A run stopped by its deadline counts as caught
  and is reported, since the test should fail on its own instead of hanging.

### Added

- `tests/run-bounded.sh`, run in CI; `tests/compose.sh` checks the runner is
  installed as committed and that the implement fragment runs it.

## [1.5.0] - 2026-10-05

### Added

- `speckit-implement`: a case's expected result is never changed to reach
  green; one believed wrong is stopped, its test removed so the suite stays
  green, marked `stopped: possible spec gap` in the list, and reported. The
  story review compares each task's tests with its list.
- `tests/compose.sh` also checks that core still has the rules the fragments
  now replace: the contract test task per contract and "Tests specific to that
  story" in tasks, the test-tasks-first order and "Tests before code" in
  implement.

### Changed

- `speckit-tasks`: a behaviour task carries its test list — concrete cases
  with input and expected result, taken from the spec, simplest first, as
  plain bullets under the task line — instead of a test task before each
  implementation task. On the pilot about a fifth (7–8 of 36)
  of three `/speckit-analyze` rounds' findings corrected predicted failures; tasks no
  longer predict them.
- `speckit-implement`: one cycle per case of the list, with the command and
  failure line of each red run recorded under the case; a case found mid-run
  joins its task's list; a task closes when every case is taken, and its list
  stays for the review. A tasks.md from an earlier version still works: a
  test task and its implementation task are read as one task.
- Stop gate: installed at the first green run of the whole suite, also when
  the suite is created during the run (previously "the first task that closes
  green", which per-case cycles would have delayed).

### Removed

- Separate test tasks and predicted failures in `speckit-tasks`.

## [1.4.1] - 2026-10-05

### Fixed

- Stop gate: a project with a gate of its own — a Stop hook whose command
  or script runs the suite, or a subset, and exits 2 when it is red — no longer gets a
  second one. Found updating a project that had a hand-written gate under
  another name, which the hook-path check could not see; the installer cannot
  tell what another hook does, so the fragment reads each entry's script. A
  Stop hook that runs tests only to notify or log does not count.
- Installer: the gate's commit message showed the test command with its
  quoting lost (`sh -c CI=1 npm test` for `sh -c 'CI=1 npm test'`), present
  since `sdd-gate`. It now shows it quoted exactly as the hook's
  `TEST_COMMAND` holds it, built once for both.

## [1.4.0] - 2026-10-05

### Added

- Stop gate: `scripts/bash/install-stop-gate.sh`, and a `speckit-implement`
  section that runs it the first time the whole suite is green with no gate in
  place. It commits a Claude Code Stop hook that runs the suite at the end of
  every turn and blocks the first stop of a red one. Moved here from the
  `sdd-gate` command in github.com/camilopiedra92/dotfiles, which had to be run
  by hand in each repository; its tests moved with it as `tests/stop-gate.sh`.
  Run through `bash` because `specify preset add --from` drops the executable
  bit (1.1.0: a zip entry stored as 755 installs as 644).
- Installer, beyond what `sdd-gate` did: it refuses a leftover Stop entry for
  the hook, which would run the suite twice per stop, and reports a commit
  refused by a commit hook as such instead of only through the hook's own
  output. The gate is turned off by removing its Stop entry and keeping the
  hook file, which `/speckit-implement` checks for.

## [1.3.0] - 2026-10-05

### Added

- `speckit-implement` review brief: the reviewer also reads the story's code
  for what each cycle's refactor step should have removed — duplication, an
  unneeded special case, names that do not say what they hold, a function
  doing two things — and each finding is carried out as a refactor. The
  refactor step left no trace in a feature run on v1.2.0, so it is now
  checked from another context instead of self-reported. Tested on code with
  planted, behaviour-neutral duplication and bad names: the v1.2.1 brief
  caught the duplication only through the test gap it caused and named none
  of the names; this brief named both.

### Fixed

- Review brief: wrong versions run from a clean build state. A reviewer got a
  false survivor from Python's bytecode cache, which is keyed on mtime to the
  second; `PYTHONDONTWRITEBYTECODE=1` alone does not help once `__pycache__`
  exists (reproduced), so the cache is deleted first.

## [1.2.1] - 2026-10-05

### Fixed

- `speckit-implement` review brief: the reviewer first breaks something
  obvious in its scratch copy and watches the suite fail, rebuilding the
  copy's environment if it does not. An environment copied with the repo keeps
  absolute paths to the original (uv's editable `.pth`, script shebangs):
  reproduced with uv, a copy with a broken `cli.py` still passed 90 of 90, so
  every wrong version would pass and be misreported as a test gap. Rebuilding
  with `uv sync` inside the copy made it fail. Found by the first story
  review in a headless feature run on v1.2.0 (sdd-pilot, feature 002).

## [1.2.0] - 2026-10-05

### Added

- `speckit-implement`: one red-green-refactor cycle at a time, with a refactor
  step limited to what the cycle left (structure only, suite run after each
  step); a test that passes on its first run is checked by breaking the code
  it pins; a case found mid-implementation becomes a new test and
  implementation task, or a spec gap listed in the completion report; a
  baseline of the suite and the project's existing lint and type checks is
  recorded before the first task, and a task closes only with no test failure
  or static-check finding beyond it and none of its new files ignored by git
  (a test task closes on its watched failure).
- `speckit-implement`: core's "Project Setup Verification" is narrowed —
  `.gitignore` gets only patterns for generated files and may not end up
  ignoring a tracked file or one the feature means to commit; other ignore
  files and linter or formatter config are touched only when the tool is new
  to the repository in this feature.
- `speckit-tasks`: a story is a sequence of cycles — each test task
  immediately before its implementation task, neither `[P]` — ordered from
  the simplest case, replacing core's all-tests-then-models order and the
  tasks template's "Write these tests FIRST" block.
- `tests/compose.sh` fails if core drops a rule, template block or step a
  fragment replaces or narrows.

### Changed

- "Logic of its own" is now spelled out (a branch, a computation, a parse, a
  state change), so it matches the threshold in the author's global rules.

## [1.1.0] - 2026-10-05

### Added

- `speckit-implement` fragment: each completed user story gets a review from
  a fresh context (a subagent or separate session) that tries plausible wrong
  versions of the code against the tests; each gap is closed with a test
  watched failing. In the pilot that motivated it, one such review found three wrong
  versions the 67-test suite accepted, after analyze and converge passed.
- README sections on when to use the preset and when not to, and which
  integration it is verified with.

## [1.0.0] - 2026-10-05

### Added

- `speckit-tasks` fragment: test tasks required for behaviour with logic of its
  own, one behaviour per task, implementation tasks cite `FR-`/`SC-` IDs.
- `speckit-implement` fragment: a test counts once it has failed from inside;
  a task is marked done only after a passing run.
- `tests/compose.sh` and CI composing the preset against the pinned and the
  latest Spec Kit release.

[Unreleased]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.5.1...HEAD
[1.5.1]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.4.1...v1.5.0
[1.4.1]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/releases/tag/v1.0.0
