"""Drift guard for the bundled offline sample.

``frontend/lib/demoFixture.ts`` is the only data source for the Workbench's
offline demo, and it claims to be a real pipeline output. Nothing used to check
that claim, so it silently drifted: the sample still showed a REVIEW after the
engine started returning ABSTAIN for the same input, and one of its decision
paths lacked the keys ``DecisionPaths`` iterates, which crashed the tab.

This test makes the claim executable: the committed artifact must equal what
``scripts/generate_demo_fixture.py`` produces right now (wall-clock fields
excluded, since latency varies per run).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_demo_fixture.py"
ARTIFACT = ROOT / "frontend" / "lib" / "demoFixture.ts"


def _generator():
    spec = importlib.util.spec_from_file_location("generate_demo_fixture", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _artifact_payload() -> dict:
    text = ARTIFACT.read_text(encoding="utf-8")
    return json.loads(text[text.index("= {") + 2 : text.rindex("} as DemoFixture;") + 1])


def test_bundled_sample_matches_the_current_pipeline():
    module = _generator()
    generated = module.render()
    committed = ARTIFACT.read_text(encoding="utf-8")
    assert module.comparable(generated) == module.comparable(committed), (
        "frontend/lib/demoFixture.ts is stale; run "
        "python scripts/generate_demo_fixture.py"
    )


def test_bundled_sample_projection_covers_every_declared_field():
    """The sample must not silently drop a field the frontend type declares."""
    keys, optional = _generator().declared_assessment_keys()
    payload = _artifact_payload()["assessment"]
    missing = [key for key in keys if key not in payload and key not in optional]
    assert missing == [], missing


@pytest.mark.parametrize("key", ["required_inputs", "input_provenance"])
def test_every_decision_path_carries_the_keys_the_ui_iterates(key):
    """Regression: an absent key here crashed the Decision paths tab."""
    paths = _artifact_payload()["assessment"]["agent"]["decision_trace"]["paths"]
    assert paths, "the sample should contain decision paths"
    assert [path["reason_code"] for path in paths if key not in path] == []
