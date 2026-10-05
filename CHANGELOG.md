# Changelog

All notable changes to this preset are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/releases/tag/v1.0.0
