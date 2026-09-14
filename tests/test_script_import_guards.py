"""Importing a script must not run it.

Six scripts executed their whole body at import time: one overwrote two tracked
artifacts under `examples/`, one wrote a benchmark file, one polled for 90
seconds, one read a required environment variable, one exited the interpreter
through `argparse` and one ran a full assessment. Any `importlib` scan, IDE
index, packaging step or `pytest --doctest-modules` run touching `scripts/` did
all of it, silently.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The six that had no `__main__` guard. Named explicitly so removing one of them
# is a visible change rather than a quietly shortened parametrisation.
GUARDED_SCRIPTS = (
    "generate_public_sample",
    "run_benchmark",
    "run_demo",
    "validate_decision_benchmark",
    "validate_postgres_migration",
    "verify_docker_health",
)


def _example_digests() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "examples").iterdir())
        if path.is_file()
    }


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", GUARDED_SCRIPTS)
def test_importing_a_script_has_no_side_effects(name: str, monkeypatch) -> None:
    # A hostile argv: without a guard, `argparse.parse_args` would call
    # `sys.exit(2)` right here.
    monkeypatch.setattr(sys, "argv", ["pytest", "--definitely-not-a-real-flag"])
    # And no DATABASE_URL, which used to raise `KeyError` on import.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    before = _example_digests()
    module = _import_script(name)
    assert hasattr(module, "main"), f"{name} exposes no main() to call"
    assert _example_digests() == before, f"importing {name} rewrote a tracked example"


def test_every_script_guards_its_entry_point() -> None:
    offenders = [
        path.name
        for path in sorted((ROOT / "scripts").glob("*.py"))
        if 'if __name__ == "__main__":' not in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"scripts without a __main__ guard: {offenders}"


def test_public_sample_is_regenerable_and_matches_the_committed_artifact() -> None:
    """The committed sample must be reproducible from the current code.

    It was not: the checked-in report showed 42.7/100 (Moderate) while the code
    produced 39.1/100 (Low), so the one artifact a reviewer is most likely to open
    disagreed with the software that generated it.
    """
    import json

    from finrisk.pipeline import FinRiskPipeline
    from finrisk.report import render_text_report

    data = json.loads(
        (ROOT / "research/benchmark/public_company_observations.json").read_text(
            encoding="utf-8"
        )
    )
    example = next(x for x in data["examples"] if x["id"] == "intc-2024")
    assessment = FinRiskPipeline(ROOT).assess(
        example["company"],
        example["fiscal_year"],
        example["current"],
        example["previous"],
        {int(k): v for k, v in example["pages"].items()},
        f"{example['company']} FY{example['fiscal_year']} annual report",
    )
    committed = (ROOT / "examples/intel_2024_sample_report.txt").read_text(
        encoding="utf-8"
    )
    assert render_text_report(assessment) == committed
    assert f"Overall Risk: {assessment.overall_score}/100 ({assessment.risk_level})" in committed
