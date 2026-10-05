# Changelog

All notable changes to this preset are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.2.0] - 2026-10-05

### Added

- `speckit-implement`: a refactor step once the suite is green (structure
  only, suite run after each step); a test that passes on its first run is
  investigated rather than counted; a case found mid-implementation becomes a
  new test task, or a reported spec gap; a task closes only when the project's
  existing lint and type checks pass too, not only the suite.
- `speckit-implement`: core's "Project Setup Verification" is narrowed —
  `.gitignore` gets only patterns for generated files and never one matching a
  tracked file; other ignore files and linter or formatter config are touched
  only when plan.md introduces the tool.
- `speckit-tasks`: a story's test tasks are ordered from the simplest case.
- `tests/compose.sh` fails if core drops the "Project Setup Verification" step
  the implement fragment narrows.

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

[Unreleased]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/releases/tag/v1.0.0
