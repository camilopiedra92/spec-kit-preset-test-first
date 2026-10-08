import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "python"


@pytest.mark.parametrize("command", ["ledger", "audit"])
def test_an_older_python_is_refused_with_a_message_not_a_traceback(command: str) -> None:
    # Runs the script as an older python3 would: version_info patched before it is executed.
    probe = (
        "import sys, runpy; sys.version_info = (3, 9, 6, 'final', 0); "
        f"sys.argv = ['cli.py', '{command}']; "
        f"runpy.run_path('{SCRIPTS / 'cli.py'}', run_name='__main__')"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, input="{}", check=False
    )

    assert result.returncode == 2
    assert "needs python3 >= 3.11, found 3.9.6" in result.stderr
    assert "Traceback" not in result.stderr
