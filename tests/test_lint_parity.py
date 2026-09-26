"""Cross-platform lint parity for the trees CI lints.

Ruff has rules that only fire on one platform. ``EXE001`` (a shebang whose file is not
executable) and ``EXE002`` (an executable file with no shebang) read the POSIX permission
bits, which a Windows checkout does not have — so a file can lint clean locally and fail
``ruff check`` on the Linux runner.

That is not hypothetical here: adding ``research`` to the CI lint invocation turned three
shebang-carrying verifiers into a red pipeline, and the failure was invisible on Windows.
The Git index stores the mode in a platform-independent form, so it — not the filesystem —
is what this module checks.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The directories CI lints. Keep in step with `.github/workflows/ci.yml`.
LINTED_TREES = ("backend", "tests", "scripts", "research")

EXECUTABLE = "100755"


def _index_modes(trees: Iterable[str]) -> dict[str, str]:
    """Path -> Git index mode for every Python file in the given trees."""
    completed = subprocess.run(
        ["git", "ls-files", "--stage", "--", *trees],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("git is unavailable, so the index mode cannot be checked")
    modes: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        # "<mode> <object> <stage>\t<path>"
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) < 3 or not path.endswith(".py"):
            continue
        modes[path] = parts[0]
    return modes


def test_shebanged_python_files_are_executable_in_the_index() -> None:
    """A shebang and the executable bit travel together, or the Linux lint job fails."""
    modes = _index_modes(LINTED_TREES)
    assert modes, "no Python files were found in the Git index"

    violations = []
    for path, mode in sorted(modes.items()):
        executable = mode == EXECUTABLE
        shebang = (ROOT / path).read_bytes()[:2] == b"#!"
        if shebang and not executable:
            violations.append(f"{path}: has a shebang but index mode is {mode}, not {EXECUTABLE}")
        elif executable and not shebang:
            violations.append(f"{path}: index mode is {EXECUTABLE} but it has no shebang")

    assert not violations, (
        "EXE001/EXE002 only fire on POSIX, so this mismatch passes locally and fails CI. "
        "Either drop the shebang (these modules are invoked as `python <path>`) or set the "
        "executable bit with `git update-index --chmod=+x -- <path>`:\n" + "\n".join(violations)
    )
