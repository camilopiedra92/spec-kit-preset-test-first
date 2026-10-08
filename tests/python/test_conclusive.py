from pathlib import Path

import audit
import ledger
from helpers import git


def runner(counter: Path, script: str) -> ledger.Config:
    """A run that counts its invocations and reports what `script` prints as JUnit cases."""
    run = (
        f"echo x >> {counter}; cases=$({script}); "
        'printf "<testsuites><testsuite>%s</testsuite></testsuites>" "$cases" > {junit}'
    )
    return ledger.Config(tests=("tests/**",), sources=("src/**",), run=run)


def runs(counter: Path) -> int:
    return len(counter.read_text().splitlines()) if counter.exists() else 0


def head_tree(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD^{tree}")


def test_a_run_with_a_passing_case_is_conclusive_without_a_probe(
    repo: Path, tmp_path: Path
) -> None:
    counter = tmp_path / "count"
    config = runner(counter, 'echo \'<testcase classname="t" name="a"/>\'; : {file}')

    with audit.Replayer(repo, config) as replayer:
        seen = replayer.observe(head_tree(repo), "tests/test_a.py", deadline=30)

    assert seen == audit.Observation({"t::a": "passed"}, conclusive=True, timed_out=False)
    assert runs(counter) == 1


# pytest's report for a file that does not load: one error case named after the module
# (measured, research L7), whatever stops the load -- here a missing import or the probe.
PYTEST_LIKE = (
    "if grep -q 'import missing' {file} || grep -q 'not code' {file}; then "
    'echo \'<testcase classname="" name="tests.test_a"><error message="collection failure"/>'
    '</testcase>\'; else echo \'<testcase classname="t" name="a"/>\'; fi'
)


def commit_file(repo: Path, path: str, text: str) -> str:
    (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", path)
    return head_tree(repo)


def test_a_load_failure_matching_its_probe_is_inconclusive(repo: Path, tmp_path: Path) -> None:
    tree = commit_file(repo, "tests/test_a.py", "import missing\n")

    with audit.Replayer(repo, runner(tmp_path / "count", PYTEST_LIKE)) as replayer:
        seen = replayer.observe(tree, "tests/test_a.py", deadline=30)

    assert not seen.conclusive


def test_zero_cases_is_conclusive(repo: Path, tmp_path: Path) -> None:
    with audit.Replayer(repo, runner(tmp_path / "count", "true; : {file}")) as replayer:
        seen = replayer.observe(head_tree(repo), "tests/test_a.py", deadline=30)

    assert seen == audit.Observation({}, conclusive=True, timed_out=False)


# Vitest's report for a file that does not load: one failure case named after the file path
# (measured, research L7).
VITEST_LIKE = (
    "if grep -q 'import missing' {file} || grep -q 'not code' {file}; then "
    'echo \'<testcase classname="\'{file}\'" name="\'{file}\'"><failure type="Error"/>'
    '</testcase>\'; else echo \'<testcase classname="t" name="a"/>\'; fi'
)


def test_a_vitest_shaped_load_failure_is_inconclusive(repo: Path, tmp_path: Path) -> None:
    tree = commit_file(repo, "tests/test_a.py", "import missing\n")

    with audit.Replayer(repo, runner(tmp_path / "count", VITEST_LIKE)) as replayer:
        seen = replayer.observe(tree, "tests/test_a.py", deadline=30)

    assert not seen.conclusive


def test_tests_that_all_fail_by_assertion_are_conclusive(repo: Path, tmp_path: Path) -> None:
    tree = commit_file(repo, "tests/test_a.py", "def test_a(): assert False\n")
    failing_or_unloadable = (
        "if grep -q 'not code' {file}; then "
        'echo \'<testcase classname="" name="tests.test_a"><error/></testcase>\'; '
        'else echo \'<testcase classname="t" name="a"><failure/></testcase>\'; fi'
    )

    with audit.Replayer(repo, runner(tmp_path / "count", failing_or_unloadable)) as replayer:
        seen = replayer.observe(tree, "tests/test_a.py", deadline=30)

    assert seen == audit.Observation({"t::a": "failed"}, conclusive=True, timed_out=False)


def test_a_load_probe_past_its_deadline_is_a_timed_out_observation(repo: Path) -> None:
    from sequences import CONFIG

    tree = commit_file(repo, "tests/test_a.py", "def test_a(): # expects src/none.py X\n")
    probe_hangs = CONFIG._replace(run=CONFIG.run + " --hang-on-unloadable")

    with audit.Replayer(repo, probe_hangs) as replayer:
        seen = replayer.observe(tree, "tests/test_a.py", deadline=1)

    assert seen.timed_out
    assert not seen.conclusive
