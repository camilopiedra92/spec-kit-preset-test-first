from pathlib import Path

import audit


def test_no_file_is_no_junit(tmp_path: Path) -> None:
    assert audit.parse_junit(tmp_path / "missing.xml") is None


def junit(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "out.xml"
    path.write_text(f'<?xml version="1.0" encoding="utf-8"?>{body}')
    return path


def test_zero_cases_is_a_conclusive_empty_run(tmp_path: Path) -> None:
    path = junit(tmp_path, '<testsuites><testsuite name="pytest" tests="0"/></testsuites>')

    assert audit.parse_junit(path) == {}


def test_a_case_without_children_passes_under_classname_and_name(tmp_path: Path) -> None:
    path = junit(
        tmp_path,
        '<testsuites><testsuite tests="1">'
        '<testcase classname="tests.test_a" name="test_one"/>'
        "</testsuite></testsuites>",
    )

    assert audit.parse_junit(path) == {"tests.test_a::test_one": "passed"}


def test_failures_and_errors_fail_and_skips_and_xfails_skip(tmp_path: Path) -> None:
    path = junit(
        tmp_path,
        '<testsuites><testsuite tests="4">'
        '<testcase classname="t" name="fails"><failure message="assert 1 == 2"/></testcase>'
        '<testcase classname="t" name="errs"><error message="fixture"/></testcase>'
        '<testcase classname="t" name="skips"><skipped message="later"/></testcase>'
        '<testcase classname="t" name="xfails"><skipped type="pytest.xfail" message=""/></testcase>'
        "</testsuite></testsuites>",
    )

    assert audit.parse_junit(path) == {
        "t::fails": "failed",
        "t::errs": "failed",
        "t::skips": "skipped",
        "t::xfails": "skipped",
    }


def test_cases_in_nested_suites_are_all_found(tmp_path: Path) -> None:
    path = junit(
        tmp_path,
        '<testsuites><testsuite name="file.test.js">'
        '<testsuite name="describe"><testcase classname="file.test.js" name="a"/></testsuite>'
        '<testcase classname="file.test.js" name="b"/>'
        "</testsuite></testsuites>",
    )

    assert set(audit.parse_junit(path) or {}) == {"file.test.js::a", "file.test.js::b"}


def test_malformed_xml_is_no_junit(tmp_path: Path) -> None:
    path = junit(tmp_path, "<testsuites><testsuite")

    assert audit.parse_junit(path) is None
