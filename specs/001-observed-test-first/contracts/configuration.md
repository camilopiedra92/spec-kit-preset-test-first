# Contract: `.specify/test-first.json`

```json
{
  "tests": ["tests/**"],
  "sources": ["src/**"],
  "run": "uv run --no-sync python -m pytest -q -p no:cacheprovider --junitxml={junit} {files}"
}
```

- Read by the hook (classification) and the audit (classification and replays).
- `{files}`: the test files to run, as repository-relative paths, shell-quoted, space-separated.
- `{junit}`: an absolute path the command writes JUnit XML to.
- `{root}`: the absolute path of the worktree the audit was run from, so a replay can reuse its
  installed environment (e.g. `UV_PROJECT_ENVIRONMENT={root}/.venv`).
- The command runs with the scratch worktree as its working directory, through `sh -c`.
- The command's exit status is ignored; only the JUnit file is read.
