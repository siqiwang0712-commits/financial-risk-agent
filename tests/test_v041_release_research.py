from __future__ import annotations

import json
from pathlib import Path

from scripts import e5_preflight, generate_v041_runtime_identities

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_identities_match_current_source() -> None:
    checked = json.loads(
        (ROOT / "research/v041_development/runtime_identities.json").read_text()
    )
    assert checked == generate_v041_runtime_identities.build()
    assert checked["assurance_policy"]["maturity"] == "HEURISTIC_POLICY"
    assert checked["assurance_policy"]["calibration_status"] == "UNCALIBRATED"
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
