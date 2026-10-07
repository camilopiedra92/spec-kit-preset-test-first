"""The ledger: a Claude Code PostToolUse hook that records the worktree after every tool call."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG = Path(".specify") / "test-first.json"


@dataclass(frozen=True)
class Config:
    tests: tuple[str, ...]
    sources: tuple[str, ...]
    run: str


def load_config(root: Path) -> Config:
    raw = json.loads((root / CONFIG).read_text())
    return Config(tests=tuple(raw["tests"]), sources=tuple(raw["sources"]), run=raw["run"])
