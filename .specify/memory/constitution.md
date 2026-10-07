# Test-first Preset Constitution

## Core Principles

### I. Append, Never Replace

The preset appends fragments to core Spec Kit skills and replaces none of them, so upstream changes
to the rest of each skill keep arriving. A fragment carries no frontmatter, because a description
there replaces the skill's own. A fragment that overrides or narrows a core rule names that rule,
and the composition test fails when core no longer carries it.

Rationale: a replaced skill freezes core at the version it was copied from, and a project would
stop receiving upstream fixes without anyone noticing. Check: `tests/compose.sh` verifies that each
composed skill keeps its core body and description and ends with its fragment, and greps core for
every rule a fragment overrides.

### II. Verified Against the Real CLI

Every change is verified by installing the preset from a tag-shaped archive with the real `specify`
CLI, against the pinned Spec Kit release on every push and pull request, and against the latest
release weekly. The pinned release moves together with `requires.speckit_version` in `preset.yml`.

Rationale: the preset's behaviour is what the CLI composes, not the fragment files; the weekly run
against the latest release is the only way an upstream change reaches this repository before it
reaches a project. Check: `.github/workflows/ci.yml` (`SPECKIT_PINNED`, the `pinned`/`latest`
matrix); a reviewer checks that a change to `SPECKIT_PINNED` also changes `requires.speckit_version`.

### III. Every Rule Has Its Evidence

A rule added to a fragment, changed or dropped carries its evidence in the README: a primary source
(a paper, vendor documentation, a practitioner's canon) or a measured run of the preset, dated and
with the Spec Kit version it ran on. An alternative that was measured or considered and not adopted
is recorded with the reason. A measurement states what was compared and how many runs, and is
called directional when it is one run per arm.

Rationale: the fragments are instructions to an agent; without evidence a rule cannot be weighed
against its cost when the next version is decided. Check: a reviewer looks for the README entry
(the "Why this shape" sources or a release's measurement) of every changed rule, and for the
CHANGELOG entry that describes it.

### IV. Scripts Fail Closed and Bounded

A script the preset ships refuses rather than guesses: a precondition it cannot verify stops it
with a message, and a refused or failed run leaves the repository as it found it. Anything that
runs a test suite or a command it does not control runs it under a deadline that kills the
command's whole process group.

Rationale: these scripts run inside other people's repositories and at the end of every agent
turn; a guess there commits the wrong thing, and an unbounded child kept a wrong version running
for hours (CHANGELOG 1.5.1). Check: `tests/stop-gate.sh` (refusals, an unchanged repository on
refusal or failure, the hook's answers to a green, red and hung suite and a missing runner) and
`tests/run-bounded.sh` (commands built to escape the deadline).

### V. Released by Tag

Projects install the preset from a tag's archive, so a release is a tag with a matching version in
`preset.yml`, a CHANGELOG entry in Keep a Changelog form, and semantic versioning: MAJOR when a
project's existing tasks, hooks or files stop working as before, MINOR for a rule or script added,
PATCH for a fix. What is not part of the preset is `export-ignore`.

Rationale: the archive is the artifact; a file in the repository that is not export-ignored lands
in every project that installs it. Check: `tests/compose.sh` builds the archive with `git archive`
as GitHub does and fails if the installed preset carries this repository's `.specify/`, `.claude/`
or `specs/`; a reviewer checks that `preset.yml`, the CHANGELOG and the tag agree.

## Governance

This constitution overrides any other practice in this repository where they conflict.

- Changes reach `main` only through pull requests; the ruleset declared in
  `camilopiedra92/dotfiles` (`github/repos.json`) requires the `compose (pinned)` check, and the
  merge is `gh pr merge --auto`.
- The owner (camilopiedra92) reviews every pull request against these principles, including
  changes made outside the Spec Kit commands.
- Amendments: the owner proposes or approves a change to this file in a pull request of its own, or
  inside the feature whose decision requires it. The commit message carries the impact report:
  version change, principles changed, what still has to exist for a new principle to be met.
- Versioning of this file: MAJOR for a principle removed or redefined incompatibly, MINOR for a
  principle or section added or materially expanded, PATCH for wording.

**Version**: 1.0.0 | **Ratified**: 2026-10-07 | **Last Amended**: 2026-10-07
