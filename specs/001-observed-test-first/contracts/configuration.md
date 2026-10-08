# Contract: `.specify/test-first.json`

```json
{
  "tests": ["tests/**"],
  "sources": ["src/**"],
  "run": "PYTHONPATH=src UV_PROJECT_ENVIRONMENT={root}/.venv uv run --no-sync python -m pytest -q -p no:cacheprovider --junitxml={junit} {file}"
}
```

- Read by the hook (classification) and the audit (classification and runs).
- `tests`: every path on the test side — test files and their support (helpers, `conftest.py`,
  fixture data). Everything else is the rest side, code included (data-model.md).
- `sources`: the project's code; used for the hook's message, for naming `born-with-code`, and for
  the no-sources run.
- `{file}`: one test file to run, as a repository-relative path, shell-quoted. The audit runs one
  file per run, so a file that fails to load cannot hide another's results (research R6). A runner
  that cannot run one file on its own (Go, whose unit is the package) is not supported.
- `{junit}`: an absolute path inside the audit's temporary directory, which the command writes
  JUnit XML to.
- `{root}`: the absolute path of the worktree the audit was run from, so a run can reuse its
  installed environment (e.g. `UV_PROJECT_ENVIRONMENT={root}/.venv`). An environment that imports
  the project's code from `{root}` (an editable install, a workspace link) would test the real
  worktree instead of the scratch one; the no-sources run detects it where a pass is accepted
  (research R7).
- The command runs with the scratch worktree as its working directory, through `sh -c`.
- The command's exit status is ignored; only the JUnit file is read.
