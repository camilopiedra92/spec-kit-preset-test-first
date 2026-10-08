import json
from pathlib import Path

import pytest

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


VALID = {"tests": ["tests/**"], "sources": ["src/**"], "run": "pytest --junitxml={junit} {file}"}


def test_empty_tests_is_an_error_naming_the_field(tmp_path: Path) -> None:
    write_config(tmp_path, {**VALID, "tests": []})

    with pytest.raises(ledger.ConfigError, match="tests"):
        ledger.load_config(tmp_path)


@pytest.mark.parametrize("bad", ["tests/**", [1], None, [""]])
def test_tests_not_a_list_of_strings_is_an_error_naming_the_field(
    tmp_path: Path, bad: object
) -> None:
    write_config(tmp_path, {**VALID, "tests": bad})

    with pytest.raises(ledger.ConfigError, match="tests"):
        ledger.load_config(tmp_path)


@pytest.mark.parametrize("bad", [[], "src/**", [3]])
def test_sources_not_a_non_empty_list_of_globs_is_an_error_naming_the_field(
    tmp_path: Path, bad: object
) -> None:
    write_config(tmp_path, {**VALID, "sources": bad})

    with pytest.raises(ledger.ConfigError, match="sources"):
        ledger.load_config(tmp_path)


@pytest.mark.parametrize(
    ("run", "named"),
    [("pytest --junitxml={junit}", "{file}"), ("pytest {file}", "{junit}"), (7, "run")],
)
def test_run_without_a_placeholder_is_an_error_naming_it(
    tmp_path: Path, run: object, named: str
) -> None:
    write_config(tmp_path, {**VALID, "run": run})

    with pytest.raises(ledger.ConfigError, match=named.replace("{", r"\{")):
        ledger.load_config(tmp_path)


def test_run_may_name_the_root(tmp_path: Path) -> None:
    run = "UV_PROJECT_ENVIRONMENT={root}/.venv pytest --junitxml={junit} {file}"
    write_config(tmp_path, {**VALID, "run": run})

    assert ledger.load_config(tmp_path).run == run


def test_a_missing_file_is_not_installed_not_malformed(tmp_path: Path) -> None:
    with pytest.raises(ledger.NotInstalled):
        ledger.load_config(tmp_path)


def test_invalid_json_is_an_error_with_the_parsers_message(tmp_path: Path) -> None:
    (tmp_path / ".specify").mkdir()
    (tmp_path / ".specify" / "test-first.json").write_text("{not json")

    with pytest.raises(ledger.ConfigError, match="Expecting property name"):
        ledger.load_config(tmp_path)


def test_a_json_value_that_is_not_an_object_is_an_error(tmp_path: Path) -> None:
    write_config(tmp_path, ["tests/**"])

    with pytest.raises(ledger.ConfigError, match="JSON object"):
        ledger.load_config(tmp_path)
