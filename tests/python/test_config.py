import json
from pathlib import Path

import ledger


def write_config(root: Path, value: object) -> None:
    (root / ".specify").mkdir(exist_ok=True)
    (root / ".specify" / "test-first.json").write_text(json.dumps(value))


def test_a_valid_file_gives_its_configuration(tmp_path: Path) -> None:
    write_config(
        tmp_path,
        {"tests": ["tests/**"], "sources": ["src/**"], "run": "pytest --junitxml={junit} {file}"},
    )

    config = ledger.load_config(tmp_path)

    assert config == ledger.Config(
        tests=("tests/**",), sources=("src/**",), run="pytest --junitxml={junit} {file}"
    )
