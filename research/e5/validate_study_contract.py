"""Validate the authoritative, deliberately unfrozen E5 study contract.

This validator reads design metadata only. It does not enumerate a cohort, load outcomes,
train a model, produce a prediction, or create a freeze manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

E5_DIR = Path(__file__).resolve().parent
REPO_ROOT = E5_DIR.parents[1]
HARNESS_DIR = E5_DIR / "harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

import e5_harness

CONFIG_PATH = E5_DIR / "experiment_config.json"
PROTOCOL_PATH = E5_DIR / "STUDY_PROTOCOL_DRAFT.md"
LEGACY_PROTOCOL_PATH = E5_DIR / "protocol" / "STUDY_PROTOCOL.md"
LEGACY_CONFIG_PATH = E5_DIR / "protocol" / "experiment_config.json"


class ContractValidationError(ValueError):
    """Raised when current E5 protocol metadata contradicts its unfrozen state."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{path} must contain a JSON object")
    return payload


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return _read_json(path)


def validate(config: dict[str, Any] | None = None) -> list[str]:
    config = config or load_config()
    checks: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ContractValidationError(message)
        checks.append(message)

    require(config.get("schema_version") == "1", "schema version is 1")
    require(config.get("study_id") == "E5", "study identity is E5")
    require(config.get("status") == "DRAFT_NOT_FROZEN", "config remains DRAFT_NOT_FROZEN")

    authority = config.get("authoritative_protocol") or {}
    require(authority.get("path") == "research/e5/STUDY_PROTOCOL_DRAFT.md", "authority path is canonical")
    require(authority.get("status") == config["status"], "protocol/config statuses agree")
    require(authority.get("freeze_allowed") is False, "protocol freeze is not allowed")
    require(PROTOCOL_PATH.is_file(), "authoritative protocol exists")
    protocol = PROTOCOL_PATH.read_text(encoding="utf-8")
    require("DRAFT_NOT_FROZEN — AUTHORITATIVE E5 STUDY CONTRACT" in protocol, "protocol declares draft authority")
    require("E5_PROTOCOL_FREEZE_ALLOWED = false" in protocol, "protocol declares freeze blocked")

    arms = config.get("conceptual_arms") or []
    arm_ids = [arm.get("id") for arm in arms]
    require(arm_ids == ["S0", "S1", "S2", "S3", "S4"], "S0-S4 occur exactly once and in order")
    require(len(set(arm_ids)) == 5, "conceptual arm identifiers are unique")
    for arm_id in arm_ids:
        require(f"### {arm_id} —" in protocol, f"protocol defines {arm_id}")

    anchors = {item.get("id"): item for item in config.get("historical_anchors") or []}
    require(set(anchors) == {"B0", "B6"}, "B0 and B6 are the only historical anchors")
    require(
        all(item.get("primary_competitive_reference") is False for item in anchors.values()),
        "B0 and B6 are not primary competitive references",
    )
    require(
        all(item.get("role") == "HISTORICAL_REFERENCE_AND_INTERPRETABILITY_ANCHOR" for item in anchors.values()),
        "B0 and B6 have historical-only roles",
    )

    strong = config.get("strong_tabular_reference") or {}
    require(strong.get("contract") == "StrongTabularReference-v1", "strong reference contract is named")
    require(strong.get("status") == "DRAFT_NOT_FROZEN", "strong reference remains unfrozen for E5")
    require(strong.get("model_selected") is True, "historical strong-reference model is selected")
    require(strong.get("fitted_artifact_exists") is True, "historical fitted strong-reference artifact exists")
    strong_config = _read_json(REPO_ROOT / strong["config"])
    require(strong_config.get("status") == "DRAFT_NOT_FROZEN", "referenced strong-reference config is unfrozen")
    strong_identity = _read_json(REPO_ROOT / strong["contract_identity"])
    require(strong_identity.get("status") == "DRAFT_NOT_FROZEN", "strong-reference contract identity is unfrozen")
    require(strong.get("contract_sha256") == strong_identity.get("contract_sha256"), "strong-reference contract hash is bound")
    require(strong.get("schema_sha256") == strong_identity.get("components", {}).get("feature_schema_sha256"), "strong-reference schema hash is bound")
    fitted = _read_json(REPO_ROOT / strong["fitted_artifact"])
    require(
        strong.get("fitted_artifact_hash") == fitted.get("hashes", {}).get("fitted_artifact_hash"),
        "historical fitted-artifact hash is bound",
    )
    require(
        fitted.get("status") == "FITTED_HISTORICAL_NOT_E5_FROZEN"
        and fitted.get("hashes", {}).get("e5_freeze_identity") == "TO_BE_FROZEN",
        "historical fitted artifact is not an E5 freeze",
    )
    require(
        strong.get("development_data_status") == "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT",
        "strong-reference development data is approved for historical development",
    )
    require(
        strong.get("development_data_approval_required_before_fit") is True,
        "development-data approval precedes S0 fitting",
    )
    require(
        strong.get("exclude_all_approved_development_companies_from_e5") is True,
        "all approved development companies must be excluded from E5",
    )
    development_proposal = _read_json(REPO_ROOT / strong["development_data_proposal"])
    require(
        development_proposal.get("status") == "PROPOSED_NOT_APPROVED",
        "original development-data proposal remains an immutable proposal record",
    )
    development_manifest = _read_json(REPO_ROOT / strong["development_data_manifest"])
    require(
        development_manifest.get("status") == "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT",
        "approved development-data manifest is bound",
    )

    calibration = config.get("calibration") or {}
    require(calibration.get("score_status") == "UNCALIBRATED", "scores remain UNCALIBRATED")
    require(
        calibration.get("resolution_status") == "RESOLVED_AS_UNCALIBRATED_FOR_V0.4.1",
        "v0.4.1 calibration is resolved as UNCALIBRATED",
    )
    require(calibration.get("probability_interpretation_allowed") is False, "probability interpretation is forbidden")

    cohort = config.get("cohort") or {}
    require(cohort.get("status") == "NOT_ENUMERATED", "cohort is not enumerated")
    require(cohort.get("enumerated") is False, "cohort enumeration flag is false")
    outcomes = config.get("outcomes") or {}
    require(outcomes.get("status") == "NOT_ACCESSED", "outcomes are not accessed")
    require(outcomes.get("accessed") is False, "outcome access flag is false")
    require(outcomes.get("artifacts_exist") is False, "no E5 outcome artifact is declared")
    predictions = config.get("predictions") or {}
    require(predictions.get("status") == "NOT_GENERATED", "predictions are not generated")
    require(predictions.get("artifacts_exist") is False, "no E5 prediction artifact is declared")

    narrative = config.get("narrative_study") or {}
    require(narrative.get("merge_with_structured_e5") is False, "E5-Narrative is separate")
    narrative_config = _read_json(REPO_ROOT / narrative["config"])
    require(narrative_config.get("merge_with_structured_e5") is False, "narrative config forbids merging")
    require("STUDY_PROTOCOL_DRAFT.md" in narrative_config.get("separate_from", ""), "narrative points to current authority")

    governance = config.get("governance") or {}
    require(governance.get("protocol_freeze_allowed") is False, "governance blocks protocol freeze")
    require(governance.get("protocol_freeze_path") == authority["path"], "harness protocol path agrees")
    require(governance.get("config_freeze_path") == "research/e5/experiment_config.json", "harness config path agrees")
    require(governance.get("stage_order") == [stage.name for stage in e5_harness.STAGES], "stage order matches active harness")
    require(e5_harness.PROTOCOL_DOCUMENT == PROTOCOL_PATH, "active harness hashes authoritative protocol")
    require(e5_harness.CONFIG_DOCUMENT == CONFIG_PATH, "active harness hashes authoritative config")
    manifests = e5_harness.load_manifests(e5_harness.DEFAULT_STAGE_DIR)
    require(not manifests, "no E5 freeze-stage manifest exists")

    legacy_protocol = LEGACY_PROTOCOL_PATH.read_text(encoding="utf-8")
    legacy_config = _read_json(LEGACY_CONFIG_PATH)
    require("LEGACY DESIGN MATERIAL — NOT A FREEZE CANDIDATE" in legacy_protocol, "legacy protocol is visibly ineligible")
    require(legacy_config.get("freeze_eligible") is False, "legacy config is freeze-ineligible")
    require(legacy_config.get("authoritative_config") == "research/e5/experiment_config.json", "legacy config points to current authority")

    prerequisites = config.get("freeze_prerequisites") or {}
    require(prerequisites.get("authoritative_contract_reconciled") == "READY", "contract reconciliation is ready")
    require(any(value in {"BLOCKED", "TO_BE_FROZEN"} for value in prerequisites.values()), "freeze prerequisites remain unresolved")
    return checks


def main() -> int:
    checks = validate()
    print(json.dumps({"status": "PASS", "checks": len(checks), "study_status": "DRAFT_NOT_FROZEN"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
