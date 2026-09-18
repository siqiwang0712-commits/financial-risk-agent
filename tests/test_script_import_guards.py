"""Importing a script must not run it.

Several `scripts/*.py` files used to execute their whole body at module level, so
a plain `import` (test collector, IDE indexer, packaging step) would connect to a
database and run migrations, overwrite the committed `examples/` artifacts, or
start making HTTP requests. This test makes the guard executable: it imports
every script in a fresh interpreter and asserts nothing happened.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "scripts").glob("*.py"))
BACKEND = ROOT / "backend"

IMPORT_DRIVER = """
import importlib.util, sys, traceback
failures = []
for path in sys.argv[1:]:
    name = "guard_" + path.rsplit("/", 1)[-1].rsplit("\\\\", 1)[-1][:-3]
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except BaseException as exc:
        failures.append((path, type(exc).__name__, str(exc)[:200]))
        print("FAILED", path, type(exc).__name__, str(exc)[:200], flush=True)
print("IMPORTED", len(sys.argv) - 1, "modules;", len(failures), "failure(s)")
"""


def _tree_hash(paths) -> dict[str, str]:
    digests = {}
    for path in paths:
        if path.is_file():
            digests[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def test_every_script_can_be_imported_without_running():
    assert SCRIPTS, "no scripts found"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND)
    env.pop("DATABASE_URL", None)
    proc = subprocess.run(
        [sys.executable, "-c", IMPORT_DRIVER, *[str(path) for path in SCRIPTS]],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"importing a script exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
    assert "FAILED" not in proc.stdout, proc.stdout
    assert f"IMPORTED {len(SCRIPTS)} modules; 0 failure(s)" in proc.stdout, proc.stdout


def test_importing_scripts_does_not_rewrite_committed_artifacts():
    watched = sorted((ROOT / "examples").glob("*")) + sorted((ROOT / "research" / "results" / "public_v1").glob("*"))
    before = _tree_hash(watched)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND)
    env.pop("DATABASE_URL", None)
    subprocess.run(
        [sys.executable, "-c", IMPORT_DRIVER, *[str(path) for path in SCRIPTS]],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=300,
        check=False,
    )

    after = _tree_hash(watched)
    changed = sorted(name for name in before if before[name] != after.get(name))
    assert changed == [], f"importing scripts rewrote: {changed}"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_script_declares_a_main_entry_point(script: Path):
    text = script.read_text(encoding="utf-8")
    assert "def main(" in text, f"{script.name} has no main()"
    assert '__name__ == "__main__"' in text, f"{script.name} has no __main__ guard"
