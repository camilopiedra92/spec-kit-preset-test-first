"""The ledger: a Claude Code PostToolUse hook that records the worktree after every tool call."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG = Path(".specify") / "test-first.json"


class NotInstalled(Exception):
    """The repository has no configuration: the ledger is not installed there."""


class ConfigError(Exception):
    """The configuration file exists but is not valid."""


@dataclass(frozen=True)
class Config:
    tests: tuple[str, ...]
    sources: tuple[str, ...]
    run: str


def load_config(root: Path) -> Config:
    try:
        text = (root / CONFIG).read_text()
    except FileNotFoundError:
        raise NotInstalled(str(root / CONFIG)) from None
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{CONFIG}: {error}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG}: must be a JSON object")
    return Config(tests=_globs(raw, "tests"), sources=_globs(raw, "sources"), run=_run(raw))


def _globs(raw: dict[str, object], field: str) -> tuple[str, ...]:
    value = raw.get(field)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(glob, str) and glob for glob in value)
    ):
        raise ConfigError(f"{CONFIG}: {field} must be a non-empty list of globs")
    return tuple(value)


def _run(raw: dict[str, object]) -> str:
    run = raw.get("run")
    if not isinstance(run, str):
        raise ConfigError(f"{CONFIG}: run must be a command string")
    for placeholder in ("{file}", "{junit}"):
        if placeholder not in run:
            raise ConfigError(f"{CONFIG}: run must contain {placeholder}")
    return run
