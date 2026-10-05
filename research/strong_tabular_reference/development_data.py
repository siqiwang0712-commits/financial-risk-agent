"""Validate development-data contracts without loading rows or fitting models."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from .contract import artifact_sha256, load_schema

HERE = Path(__file__).resolve().parent
TEMPLATE_PATH = HERE / "development_data_manifest.template.json"
PROPOSAL_PATH = HERE / "development_data_proposal.json"

ALLOWED_STATUSES = {
    "DRAFT_NOT_FROZEN",
    "PROPOSED_NOT_APPROVED",
    "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT",
}
UNRESOLVED_PREFIXES = ("TO_BE_", "UNRESOLVED", "PENDING_")
APPROVED_BLOCKS = {"V", "VO"}


class DevelopmentDataError(ValueError):
    """Raised when development data would violate the prospective isolation contract."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DevelopmentDataError(f"{path.name} must contain a JSON object")
    return value


def load_template(path: Path = TEMPLATE_PATH) -> dict[str, Any]:
    return _read_json(path)


def load_proposal(path: Path = PROPOSAL_PATH) -> dict[str, Any]:
    return _read_json(path)


def canonical_manifest_sha256(manifest: dict[str, Any]) -> str:
    """Hash a manifest while excluding only its self-referential hash field."""

    payload = deepcopy(manifest)
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        raise DevelopmentDataError("integrity object is required")
    integrity.pop("canonical_manifest_sha256", None)
    return artifact_sha256(payload)


def _unresolved(value: object) -> bool:
    if isinstance(value, str):
        return value.startswith(UNRESOLVED_PREFIXES)
    if isinstance(value, list):
        return any(_unresolved(item) for item in value)
    if isinstance(value, dict):
        return any(_unresolved(item) for item in value.values())
    return False


def _parse_date(value: object, field: str, allow_unresolved: bool) -> date | None:
    if allow_unresolved and _unresolved(value):
        return None
    if not isinstance(value, str):
        raise DevelopmentDataError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DevelopmentDataError(f"{field} must be an ISO date") from exc


def _walk_strings(value: object):
    if isinstance(value, str):
        yield value.casefold().replace("\\", "/")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key).casefold()
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def validate_development_data_manifest(
    manifest: dict[str, Any], *, schema: dict[str, Any] | None = None
) -> None:
    """Validate a draft, proposal, or future approved development-data manifest."""

    schema = schema or load_schema()
    status = manifest.get("status")
    if status not in ALLOWED_STATUSES:
        raise DevelopmentDataError("invalid development-data status")
    allow_unresolved = status != "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT"
    if manifest.get("schema_version") != "1":
        raise DevelopmentDataError("manifest schema_version must be '1'")
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise DevelopmentDataError("dataset identity is required")
    if status == "PROPOSED_NOT_APPROVED" and _unresolved(dataset_id):
        raise DevelopmentDataError("a proposal requires a nominated dataset identity")

    population = manifest.get("population") or {}
    if population.get("primary_empirical_source") is not True:
        raise DevelopmentDataError("the primary development proposal must be empirical")
    if population.get("synthetic_only") is not False:
        raise DevelopmentDataError("synthetic-only data cannot be the primary empirical dataset")

    temporal = manifest.get("temporal_contract") or {}
    feature_start = _parse_date(temporal.get("feature_start"), "feature_start", allow_unresolved)
    feature_end = _parse_date(temporal.get("feature_end"), "feature_end", allow_unresolved)
    outcome_start = _parse_date(temporal.get("outcome_start"), "outcome_start", allow_unresolved)
    outcome_end = _parse_date(temporal.get("outcome_end"), "outcome_end", allow_unresolved)
    if feature_start and feature_end and feature_start > feature_end:
        raise DevelopmentDataError("feature period is not ordered")
    if outcome_start and outcome_end and outcome_start > outcome_end:
        raise DevelopmentDataError("outcome period is not ordered")
    if feature_end and outcome_start and feature_end >= outcome_start:
        raise DevelopmentDataError("feature period must end before outcome period")

    endpoint = manifest.get("endpoint") or {}
    if not endpoint.get("name") or not endpoint.get("version"):
        raise DevelopmentDataError("endpoint name and version are required")
    if status == "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT" and str(
        endpoint.get("compatibility_status", "")
    ).startswith(("NOT_COMPATIBLE", "UNRESOLVED")):
        raise DevelopmentDataError("an incompatible or unresolved endpoint cannot be approved")

    feature = manifest.get("feature_contract") or {}
    if feature.get("feature_schema_version") != schema.get("schema_version"):
        raise DevelopmentDataError("feature-schema version mismatch")
    if feature.get("feature_schema_sha256") != artifact_sha256(schema):
        raise DevelopmentDataError("feature-schema hash mismatch")
    blocks = feature.get("permitted_feature_blocks")
    if not isinstance(blocks, list) or not blocks or not set(blocks) <= APPROVED_BLOCKS:
        raise DevelopmentDataError("incompatible feature block declaration")

    isolation = manifest.get("isolation") or {}
    if isolation.get("same_company_rows_must_remain_grouped") is not True:
        raise DevelopmentDataError("company grouping semantics are required")
    if isolation.get("company_group_key") not in {"company_id", "cik"}:
        raise DevelopmentDataError("company grouping key must be company_id or cik")
    if isolation.get("e5_artifacts_referenced") is not False:
        raise DevelopmentDataError("E5 artifacts must not be referenced")
    if isolation.get("e5_future_exclusion_obligation") is not True:
        raise DevelopmentDataError("every development company must become an E5 exclusion")
    if not isolation.get("e5_exclusion_scope"):
        raise DevelopmentDataError("E5 future-exclusion scope is required")

    label_access = manifest.get("label_access") or {}
    if label_access.get("historical_development_labels_may_be_used") is not True:
        raise DevelopmentDataError("historical label-access semantics are missing")
    if label_access.get("e5_outcomes_forbidden") is not True:
        raise DevelopmentDataError("E5 outcomes must be forbidden")
    forbidden = ("e5_outcomes.json", "e5_outcome_manifest", "future_e5_outcome")
    if any(any(token in text for token in forbidden) for text in _walk_strings(manifest)):
        raise DevelopmentDataError("forbidden E5 outcome reference")

    provenance = manifest.get("provenance") or {}
    if provenance.get("hash_verification_status") == "VERIFIED":
        hashes = provenance.get("source_artifact_hashes")
        if not isinstance(hashes, dict) or not hashes:
            raise DevelopmentDataError("verified provenance requires source hashes")
        if any(
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in hashes.values()
        ):
            raise DevelopmentDataError("verified provenance contains an unresolved source hash")

    forbidden_artifact_keys = {"model", "predictions", "fitted_model", "cv_results"}
    if forbidden_artifact_keys & set(manifest):
        raise DevelopmentDataError("development-data manifest must not contain model artifacts")

    if status == "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT":
        if _unresolved(manifest):
            raise DevelopmentDataError("approved manifest contains unresolved required fields")
        gates = manifest.get("eligibility_gates") or {}
        if not gates or any(value != "PASS" for value in gates.values()):
            raise DevelopmentDataError("approved manifest requires every eligibility gate to PASS")
        recorded_hash = (manifest.get("integrity") or {}).get("canonical_manifest_sha256")
        if recorded_hash != canonical_manifest_sha256(manifest):
            raise DevelopmentDataError("approved manifest canonical hash mismatch")


def main() -> int:
    schema = load_schema()
    template = load_template()
    proposal = load_proposal()
    validate_development_data_manifest(template, schema=schema)
    validate_development_data_manifest(proposal, schema=schema)
    print(
        json.dumps(
            {
                "status": "PASS",
                "template_status": template["status"],
                "proposal_status": proposal["status"],
                "proposal_sha256": canonical_manifest_sha256(proposal),
                "models_trained": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
