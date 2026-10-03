"""Boundary tests for the authoritative, deliberately unfrozen E5 contract."""

from __future__ import annotations

import copy

import pytest

from research.e5 import validate_study_contract


def _config() -> dict:
    return copy.deepcopy(validate_study_contract.load_config())


def _rejected(config: dict, message: str) -> None:
    with pytest.raises(validate_study_contract.ContractValidationError, match=message):
        validate_study_contract.validate(config)


def test_authoritative_contract_is_consistent_and_unfrozen() -> None:
    checks = validate_study_contract.validate()
    assert len(checks) >= 40


def test_frozen_status_is_rejected() -> None:
    config = _config()
    config["status"] = "FROZEN"
    _rejected(config, "DRAFT_NOT_FROZEN")


@pytest.mark.parametrize("arm_index", [1, 2, 3, 4])
def test_missing_or_duplicate_arm_is_rejected(arm_index: int) -> None:
    config = _config()
    config["conceptual_arms"][arm_index]["id"] = "S0"
    _rejected(config, "S0-S4")


def test_historical_anchor_cannot_become_primary_reference() -> None:
    config = _config()
    config["historical_anchors"][1]["primary_competitive_reference"] = True
    _rejected(config, "not primary competitive")


def test_strong_reference_must_remain_unfrozen_for_e5() -> None:
    config = _config()
    config["strong_tabular_reference"]["status"] = "FROZEN"
    _rejected(config, "strong reference remains unfrozen")


def test_calibration_cannot_enable_probability_interpretation() -> None:
    config = _config()
    config["calibration"]["probability_interpretation_allowed"] = True
    _rejected(config, "probability interpretation")


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("cohort", "enumerated", True, "cohort enumeration"),
        ("predictions", "artifacts_exist", True, "prediction artifact"),
        ("outcomes", "accessed", True, "outcome access"),
    ],
)
def test_execution_artifacts_are_rejected(
    section: str,
    field: str,
    value: bool,
    message: str,
) -> None:
    config = _config()
    config[section][field] = value
    _rejected(config, message)


def test_narrative_study_cannot_be_merged() -> None:
    config = _config()
    config["narrative_study"]["merge_with_structured_e5"] = True
    _rejected(config, "E5-Narrative is separate")


def test_harness_stage_order_cannot_drift() -> None:
    config = _config()
    config["governance"]["stage_order"] = list(reversed(config["governance"]["stage_order"]))
    _rejected(config, "stage order")


def test_authoritative_path_cannot_point_to_legacy_protocol() -> None:
    config = _config()
    config["authoritative_protocol"]["path"] = "research/e5/protocol/STUDY_PROTOCOL.md"
    _rejected(config, "authority path")
