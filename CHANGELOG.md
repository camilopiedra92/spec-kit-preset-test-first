# Changelog

All notable changes to this preset are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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

[Unreleased]: https://github.com/camilopiedra92/spec-kit-preset-test-first/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/camilopiedra92/spec-kit-preset-test-first/releases/tag/v1.0.0
