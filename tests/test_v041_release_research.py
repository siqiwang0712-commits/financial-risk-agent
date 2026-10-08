from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import (
    e5_preflight,
    generate_v041_runtime_identities,
    generate_v042_runtime_identities,
)

ROOT = Path(__file__).resolve().parents[1]


def test_historical_synthetic_source_retains_its_recorded_byte_identity() -> None:
    record = json.loads((ROOT / "research/v040_development/development_reference.json").read_text())
    actual = hashlib.sha256((ROOT / "examples/synthetic_company.json").read_bytes()).hexdigest()
    assert actual == record["source_fixture_sha256"]


def test_release_runtime_identities_match_immutable_historical_source() -> None:
    checked = json.loads(
        (ROOT / "research/v041_development/runtime_identities.json").read_text()
    )
    generate_v042_runtime_identities.verify_historical()
    assert checked == generate_v041_runtime_identities.build(generate_v042_runtime_identities.historical_bytes)
    assert checked["assurance_policy"]["maturity"] == "HEURISTIC_POLICY"
    assert checked["assurance_policy"]["calibration_status"] == "UNCALIBRATED"
    assert checked["decision_certificate"]["e5_freeze_identity"] == "TO_BE_FROZEN"


def test_development_runtime_identities_match_current_source() -> None:
    checked = json.loads((ROOT / "research/v042_development/runtime_identities.json").read_text())
    assert checked == generate_v042_runtime_identities.build()
    assert checked["scope"] == "RELEASE_CANDIDATE_NOT_PUBLISHED_NOT_E5_FREEZE"
    assert checked["release_identity"] == "v0.4.2"
    assert checked["decision_certificate"]["e5_freeze_identity"] == "TO_BE_FROZEN"


def test_e5_preflight_is_stage_aware_and_blocked() -> None:
    checked = json.loads(
        (ROOT / "research/e5_readiness/preflight_v041.json").read_text()
    )
    assert checked == e5_preflight.build()
    assert checked["status"] == "BLOCKED"
    assert checked["stages"]["protocol_freeze"]["status"] == "BLOCKED"
    assert checked["stages"]["cohort_freeze"]["status"] == "BLOCKED"
    assert checked["stages"]["prediction_freeze"]["status"] == "NOT_YET_APPLICABLE"
    assert checked["stages"]["outcome_unlock"]["status"] == "NOT_YET_APPLICABLE"
    assert checked["e5_executed"] is False
    assert checked["e5_frozen"] is False
