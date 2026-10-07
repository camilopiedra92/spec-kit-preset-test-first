## What goes into the constitution

The steps above give the constitution its shape. These rules decide what goes
into it, for a new project and an existing one alike.

- Every principle has a source, and the summary names it for each one:
  something the repository shows the project already does — its code, its
  configuration, its CI, its installed presets, its history — a rule its
  docs state, or a decision the user gives in this run.
- A principle already in the constitution counts as a decision the user made.
  An amendment changes only what the user asked for; a principle that breaks
  a rule below stays, and the summary lists it as a candidate for its own
  amendment.
- A project with no code of its own yet — Spec Kit and its presets do not
  count — has nothing to show, so its principles come from the user. If the
  user gave none, write nothing: end with candidate principles
  drawn from what they said they are building, each with its check, and ask
  which to ratify. The file stays as `specify init` left it until they
  answer.
- Never invent a principle to fill a slot in the template: drop the slot and
  its heading instead.
- A principle the project does not meet yet — every principle in a new
  project, a newly decided one in an existing project — still goes in, and
  the summary names what has to exist for it to be met: the check, the
  configuration, the code.
- A principle is a rule every change must meet; a SHOULD names the case in
  which it may be skipped. Rules for one phase of the
  workflow belong in a preset, decisions for one feature in that feature's
  plan, and runtime guidance — how to build, how to run the tests, where
  things live — in the agent context file (`CLAUDE.md`, `AGENTS.md`). Leave
  those out, and list each in the summary with where it belongs. If the user
  explicitly asks for one of them in the constitution, it goes in, and the
  summary says where it would otherwise belong.
- The user's global agent instructions already apply to every project, so
  they are not a source here. A practice the project follows goes in when
  the repository itself holds it — a test, a CI step, configuration, an
  installed preset — not because the global instructions require it.
- Every MUST can be checked against a change. When a command, a test or a
  search can check it, name that check in the principle; when only a reviewer
  can, say what the reviewer looks at.
- Governance names only procedures this repository can carry out: no pull
  request rule where there is no remote, no approver who does not exist.
  Each procedure names who carries it out and when.
- Neither governance nor a principle's check restates a procedure that
  `/speckit-plan`, `/speckit-implement` or an installed preset already carries
  out, such as the plan's Constitution Check gate, a preset's review or its
  record of red runs: that is its home, and a second copy drifts from it.
  Pointing to it by name is not restating; describing its steps or criteria
  is. A change made outside those commands is checked by none of them, so
  governance still names who checks it against the principles, and when.
  Amending this file and its versioning stay in governance, as the core
  template asks.

## Before the commit

The Sync Impact Report is for reviewing the amendment, not for the history.
In the final summary, put its content in the body of the suggested commit
message. If this run commits the constitution itself, take the report out of
the file first, carry it into the commit message, and confirm the committed
file no longer holds it.
