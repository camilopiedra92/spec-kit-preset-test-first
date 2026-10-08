# spec-kit-preset-constitution-authoring

A [Spec Kit](https://github.com/github/spec-kit) preset that decides what goes
into a project's constitution. It appends to the core `speckit-constitution`
skill and replaces nothing, so upstream changes to the rest of it keep
arriving. The core skill already sets the constitution's shape — a rationale
where it is not obvious, governance with versioning, the Sync Impact Report
removed before commit; this preset adds the rules for its content, for a new
project and an existing one alike:

- Every principle has a source the summary names: what the repository shows
  the project already does, a rule its docs state, or a decision the user
  gives. Nothing is invented to fill a template slot.
- Principles already ratified count as the user's decisions: an amendment
  changes only what was asked.
- A new project with no rules given gets no constitution yet: the skill
  writes nothing and asks, offering candidate principles with their checks.
  A headless run therefore ends without one.
- A principle not met yet still goes in, with what has to exist to meet it.
- Only rules every change must meet. Workflow-phase rules, feature decisions
  and runtime guidance are listed under Next Actions with where they belong,
  unless the user asks for them by name; the user's global agent
  instructions are not a source.
- Every MUST names its check: a command, a test, a search, or what a
  reviewer looks at. Governance names only procedures the repository can
  carry out, each with who carries it out and when. Neither governance nor a
  check restates what `/speckit-plan`, `/speckit-implement` or an installed
  preset already runs (naming it is fine); governance still says who checks a
  change made outside them against the principles, and when, and keeps the
  amendment and versioning policy.
- The Sync Impact Report goes into the suggested commit message.

## When to use it

- Projects whose constitution is loaded on every session (imported from
  `CLAUDE.md` or `AGENTS.md`), where every line has a cost.
- Teams that want `/speckit-analyze` and review to be able to check each
  principle against a change.

## When not to use it

- A constitution meant as an aspirational charter rather than a set of
  checkable rules: this preset will leave most of that out.

Verified with the Claude Code integration only. The fragment is plain Markdown
and should compose for any integration that registers command overrides, but
that is not tested.

## Install

```bash
specify preset add --from https://github.com/camilopiedra92/spec-kit-preset-constitution-authoring/archive/refs/tags/v1.2.0.zip
```

To move a project to a newer release:
`specify preset update constitution-authoring --from <that tag's zip URL>`.

It touches only `speckit.constitution`, so it stacks with presets on other
commands; every behaviour run below had
[spec-kit-preset-test-first](https://github.com/camilopiedra92/spec-kit-preset-test-first)
installed next to it.

Once any preset is installed, Spec Kit's bash scripts resolve templates with
`python3` and PyYAML. If the `python3` on your PATH lacks PyYAML, point
`SPECKIT_PYTHON_EXECUTABLE` at one that has it — the specify CLI's own uv tool
environment does: `$(uv tool dir)/specify-cli/bin/python`.

## Verified

`tests/compose.sh` installs the preset from a tag-shaped archive into a scratch
project with the real CLI and checks that the skill keeps its core body
verbatim and its description, and ends with the fragment. It also checks that
core still says the five things the fragment builds on: inferring from repo
context, loading an existing constitution, Next Actions, the suggested commit
message, and removing the report before commit. CI runs it against the pinned Spec Kit release on every
push and against the latest release weekly.

Behaviour, Spec Kit 1.1.0 with Claude Code, 2026-10-05: headless `claude -p`
runs, one per arm, with the author's global agent instructions loaded and the
test-first preset installed in every arm. Prompts, after `/speckit-constitution`:
*new* — "New project: a Python CLI that converts bank CSV exports into the CSV
format YNAB imports. Ratify its constitution, then commit it."; *existing* —
"Ratify the constitution from the rules this project already follows, then
commit it." on a stdlib Python CLI with one feature built and the constitution
reset to the template; *amend* — a request to add one principle to that
project's three-principle constitution.

| Case | Without the preset | With the v1.0.0 fragment |
|---|---|---|
| New | 107 lines committed, five principles, two of them copied from the global instructions | nothing written; candidate principles, each with its check, put to the user |
| Existing | 83 lines, with Toolchain and Development Workflow sections and a principle from one feature's research | 60 lines: three principles naming their checks, and governance |
| Amend | not run | the one principle added with its check, the rest untouched, MINOR bump |

Earlier drafts of the fragment gave the same shape in more runs: three for
existing (50, 53 and 55 lines), three for new (nothing written each time),
one for amend (only the asked principle added). Not observed in these runs: the
interactive path, where the user picks candidates and the skill then ratifies
them (the v1.1.0 runs below take it with every candidate accepted). With these
prompts both arms took the Sync Impact Report out of the committed file, so
these runs are not evidence for that rule.

v1.1.0, 2026-10-05, same setup, two steps resumed in one session:
`/speckit-constitution <description>` on a new project with nothing written,
then "Ratify all your candidate principles as written. The repository has no
remote. Write the constitution, add the import to CLAUDE.md, and commit." Every
candidate is accepted, so the user's choice among them is not exercised. Two
projects (the YNAB converter above and an expense splitter), two runs each per
arm. One judge scored the constitutions under labels that hid the arm, in two
batches: arms A and B together, then arm C under the same written rules, computing what
could be computed (float formatting, search patterns, set ordering). A check
is *discriminating* if a realistic change that breaks its principle fails it,
*weak* if such a change passes it or it checks something else, *reviewer* if
it is left to a named reviewer step, *vague* if that step names nothing to
look at.

| | A: v1.0.0 | B: both candidate rules | C: v1.1.0, governance rule only |
|---|---|---|---|
| Checks named | 38 | 34 | 42 |
| Discriminating | 12 (32%) | 14 (41%) | 15 (36%) |
| Weak | 18 (47%) | 16 (47%) | 20 (48%) |
| Reviewer / vague | 7 / 1 | 4 / 0 | 6 / 1 |
| Governance procedures with no actor or no time | 7 | 1 | 0 |
| "Catches X" claims refuted by computation | 0 | 3 | 0 |

Four runs per arm and one judge: directional, not a measurement of variance.
The governance rule is what shipped, measured on its own in arm C. The other
candidate rule, "a check counts only if it fails on a change that breaks its
principle; name the violation and run the check against it when it can run
now", did not: weak checks stayed at the same share, the gain in
discriminating checks was within what single runs vary by (per run: A
25–38%, B 25–57%, C 29–56%), and it added confident
claims about what a check catches that computation refuted. With no code yet,
most checks cannot be run when the constitution is written. On the expense
splitter's real constitution (one repository, outside this eval) two rounds of
review from a fresh context found the weak checks, so they are left to that
review.

v1.2.0, 2026-10-06: the rule that neither governance nor a principle's check
restates a procedure `/speckit-plan`, `/speckit-implement` or an installed
preset already runs, while governance still names who checks a change made
outside them, and when. Found on a real constitution written with v1.1.0,
whose Compliance clause restated the test-first preset's per-story review.

Same headless setup as above (the author's global instructions loaded, and
they describe that review), the *existing* prompt without the commit
("Ratify the constitution from the rules this project already follows. Do
not commit."), on a stdlib Python CLI with one feature and its tests, both
presets installed by `sdd-init`; each candidate fragment installed with
`specify preset add --dev` from a copy. The runs' allowlist did not include
`resolve-template.sh`, so every run in every arm read the template layers by
hand, a fallback the core command forbids. A constitution counts as
restating when its governance or a principle's check describes the steps or
criteria of such a procedure: what it runs, records or requires. Naming the
procedure, as the rule allows, does not count, and neither does saying which
document it judges against.

| | v1.1.0 | v1.2.0 |
|---|---|---|
| Describes the steps or criteria of a command's or preset's procedure | 3 of 3 | 0 of 3 |
| What was described | the plan gate's Complexity Tracking path (2), what the preset's per-story review runs (1), where the preset records red runs (1) | — |
| Names who checks a change made outside the commands, and when | 3 of 3 | 3 of 3 |
| States amendments and versioning | 3 of 3 | 3 of 3 |
| Principles (lines) | 3, 3, 3 (61, 68, 77) | 3, 3, 4 (67, 68, 68) |

Two earlier wordings were measured and dropped, three runs each. "Governance
does not restate…; name only what nothing else runs" described no procedure,
but one run read its last clause as "name nothing" and wrote no direct-change
procedure, and another kept only the command half of it. The next wording
also covered principle checks and kept the direct-change procedure in 3 of 3,
but it said "a Spec Kit command", which takes in `/speckit-constitution`'s
own amending and versioning, the procedure the core template asks governance
to state; one of its runs stopped before writing rather than read the
template by hand, and was repeated. One reader who knew the arms:
directional, not a measurement of variance.
