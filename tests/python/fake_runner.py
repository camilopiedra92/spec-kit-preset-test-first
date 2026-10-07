"""A stand-in test runner for the audit's units: reads one test file, writes JUnit XML.

Each `def test_<name>():` line is a test. After it, on the same line:
  `# expects <path> <text>`  fails unless <path> exists and contains <text>
  `# skip`                   is skipped
A file containing `import missing`, or the load probe's content, or a `# needs <path>` line
whose path does not exist -- in the file itself or in a shared fixture it names with
`# uses <path>` -- does not load: one error case
named after the module, with an empty classname, as pytest 9.1.1 reports it (research L7). A file
that does not exist gives a report with no case, as pytest does.

With `--root <dir>`, `# expects` paths resolve against <dir> instead of the working directory:
an environment that imports the project's code from the real worktree (an editable install).

Usage: python3 fake_runner.py <file> <junit> [--root <dir>]
"""

import re
import sys
import time
from pathlib import Path
from xml.sax.saxutils import quoteattr

TEST = re.compile(r"def (test_\w+)\(\):(.*)")


def cases(file: Path) -> list[str]:
    if not file.exists():
        return []
    text = file.read_text(errors="replace")
    module = str(file.with_suffix("")).replace("/", ".")
    shared = [Path(p) for p in re.findall(r"# uses (\S+)", text) if Path(p).exists()]
    needs = re.findall(r"# needs (\S+)", text + "".join(p.read_text() for p in shared))
    if "import missing" in text or "not code" in text or not all(map(_exists, needs)):
        return [
            f'<testcase classname="" name={quoteattr(module)}>'
            '<error message="collection failure"/></testcase>'
        ]
    found = []
    for name, rest in TEST.findall(text):
        head = f"<testcase classname={quoteattr(module)} name={quoteattr(name)}"
        expects = re.search(r"# expects (\S+) (.+)", rest)
        if "# skip" in rest:
            found.append(f"{head}><skipped/></testcase>")
        elif expects and not _holds(Path(expects.group(1)), expects.group(2).strip()):
            found.append(f'{head}><failure message="expected"/></testcase>')
        else:
            found.append(f"{head}/>")
    return found


def _exists(path: str) -> bool:
    return Path(path).exists()


CODE_ROOT = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else Path()


def _holds(path: Path, text: str) -> bool:
    path = CODE_ROOT / path
    return path.exists() and text in path.read_text(errors="replace")


if __name__ == "__main__":
    file, junit = Path(sys.argv[1]), Path(sys.argv[2])
    if file.exists() and "# hang" in file.read_text(errors="replace"):
        time.sleep(3600)
    body = "".join(cases(file))
    junit.write_text(
        f'<testsuites><testsuite tests="{body.count("<testcase")}">{body}</testsuite></testsuites>'
    )
