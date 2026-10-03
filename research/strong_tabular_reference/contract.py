"""Validation and hashing for the draft StrongTabularReference-v1 contract.

This module validates design artifacts only. It does not load outcomes, enumerate an E5
cohort, fit preprocessing, train a model, or produce predictions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "feature_schema.json"
CONFIG_PATH = HERE / "experiment_config.json"
MANIFEST_TEMPLATE_PATH = HERE / "artifact_manifest.template.json"
DEVELOPMENT_DATA_TEMPLATE_PATH = HERE / "development_data_manifest.template.json"
CONTRACT_IDENTITY_PATH = HERE / "contract_identity.json"

STATUS = "DRAFT_NOT_FROZEN"
BLOCKS = frozenset({"V", "O", "VO", "CC"})
CLASSIFICATIONS = frozenset({"FINANCIAL_VALUE", "TEMPORAL_FINANCIAL", "OBSERVABILITY"})
VALUE_CLASSES = frozenset({"FINANCIAL_VALUE", "TEMPORAL_FINANCIAL"})
APPROVED_MODEL_FAMILIES = frozenset(
    {"logistic_regression", "histogram_gradient_boosting"}
)
SEMANTIC_PENDING = frozenset(
    {
        "TO_BE_SELECTED",
        "TO_BE_FITTED",
        "TO_BE_FROZEN",
        "TO_BE_NOMINATED",
        "TO_BE_IMPLEMENTED",
        "TO_BE_PROVEN",
        "TO_BE_PROVEN_NO_OVERLAP",
    }
)
FORBIDDEN_OUTCOME_NAMES = frozenset(
    {
        "outcome",
        "label",
        "target",
        "event",
        "financial_deterioration_12m",
        "outcome_status",
        "label_status",
    }
)


class ContractError(ValueError):
    """Raised when a draft research contract violates an isolation invariant."""


def canonical_json_bytes(value: object) -> bytes:
    """Return the single canonical byte representation used by draft artifact hashes."""

    return (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def artifact_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ContractError(f"{path.name} must contain a JSON object")
    return payload


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    return _read_json(path)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return _read_json(path)


def load_manifest_template(path: Path = MANIFEST_TEMPLATE_PATH) -> dict[str, Any]:
    return _read_json(path)


def load_development_data_template(
    path: Path = DEVELOPMENT_DATA_TEMPLATE_PATH,
) -> dict[str, Any]:
    return _read_json(path)


def load_contract_identity(path: Path = CONTRACT_IDENTITY_PATH) -> dict[str, Any]:
    return _read_json(path)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _forbidden_name(name: str) -> bool:
    lowered = name.casefold()
    parts = set(lowered.replace("-", "_").split("_"))
    return lowered in FORBIDDEN_OUTCOME_NAMES or bool(parts & FORBIDDEN_OUTCOME_NAMES)


def validate_schema(schema: dict[str, Any]) -> None:
    """Fail closed on contradictory families, outcome fields, or future information."""

    if schema.get("schema_version") != "1":
        raise ContractError("feature schema_version must be '1'")
    if schema.get("status") != STATUS:
        raise ContractError(f"feature schema status must be {STATUS}")
    cutoff = schema.get("temporal_cutoff_rules") or {}
    if set(cutoff) != {
        "availability_rule",
        "current_period_rule",
        "prior_period_rule",
        "future_period_rule",
    }:
        raise ContractError("feature schema must define the complete temporal cutoff contract")

    features = schema.get("features")
    if not isinstance(features, list) or not features:
        raise ContractError("feature schema must contain a non-empty features list")

    names: set[str] = set()
    by_name: dict[str, dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            raise ContractError("each feature must be a JSON object")
        name = str(feature.get("canonical_name", ""))
        if not name or name in names:
            raise ContractError(f"feature names must be non-empty and unique: {name!r}")
        if _forbidden_name(name) or feature.get("outcome_role") != "NONE":
            raise ContractError(f"outcome-derived field is forbidden: {name}")
        if feature.get("information_timing") != "AT_OR_BEFORE_PREDICTION_CUTOFF":
            raise ContractError(f"future or unknown-period field is forbidden: {name}")
        lookback = feature.get("lookback_periods")
        if not isinstance(lookback, int) or lookback < 0:
            raise ContractError(f"lookback_periods must be a non-negative integer: {name}")

        classification = feature.get("classification")
        if classification not in CLASSIFICATIONS:
            raise ContractError(f"invalid classification for {name}: {classification}")
        blocks = set(feature.get("allowed_blocks", []))
        if not blocks or not blocks <= BLOCKS:
            raise ContractError(f"invalid allowed_blocks for {name}: {sorted(blocks)}")
        if classification in VALUE_CLASSES:
            if "O" in blocks or not blocks <= {"V", "VO", "CC"}:
                raise ContractError(f"financial value leaked into observability block: {name}")
        elif blocks != {"O", "VO"}:
            raise ContractError(f"observability feature has contradictory blocks: {name}")

        names.add(name)
        by_name[name] = feature

    for name, feature in by_name.items():
        if feature["classification"] != "OBSERVABILITY":
            continue
        observed = feature.get("observes_feature")
        if observed not in by_name or by_name[observed]["classification"] not in VALUE_CLASSES:
            raise ContractError(f"observability feature {name} has invalid target: {observed}")

    for block in BLOCKS:
        if not block_features(schema, block):
            raise ContractError(f"feature block {block} is empty")


def block_features(schema: dict[str, Any], block: str) -> tuple[str, ...]:
    if block not in BLOCKS:
        raise ContractError(f"unknown feature block: {block}")
    return tuple(
        feature["canonical_name"]
        for feature in schema.get("features", [])
        if block in feature.get("allowed_blocks", [])
    )


def validate_predictor_columns(
    columns: Iterable[str], schema: dict[str, Any], block: str
) -> tuple[str, ...]:
    """Authorize only registered, prediction-time columns for one declared block."""

    validate_schema(schema)
    supplied = tuple(columns)
    if len(set(supplied)) != len(supplied):
        raise ContractError("predictor columns must be unique")
    allowed = set(block_features(schema, block))
    for name in supplied:
        if _forbidden_name(name):
            raise ContractError(f"outcome field cannot enter model inputs: {name}")
        if name not in allowed:
            raise ContractError(f"field is not registered for block {block}: {name}")
    return supplied


def validate_config(config: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate outcome blindness and fold-local preprocessing in the draft design."""

    validate_schema(schema)
    if config.get("status") != STATUS:
        raise ContractError(f"experiment status must be {STATUS}")
    if config.get("study") != "StrongTabularReference-v1":
        raise ContractError("unexpected study identifier")
    if config.get("feature_schema_sha256") != artifact_sha256(schema):
        raise ContractError("feature schema hash does not match the checked-in schema")
    development = config.get("development_data_contract") or {}
    development_template = load_development_data_template()
    if development.get("manifest_template_sha256") != artifact_sha256(
        development_template
    ):
        raise ContractError("development-data manifest-template hash mismatch")
    if development.get("proposal_status") != "SUPERSEDED_BY_APPROVED_MANIFEST":
        raise ContractError("development-data proposal status is stale")
    if development.get("approval_status") != "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT":
        raise ContractError("development data must be mechanically approved before evaluation")
    if development.get("approval_required_before_candidate_evaluation") is not True:
        raise ContractError("development-data approval must precede candidate evaluation")
    if development.get("e5_future_exclusion_required_for_every_development_company") is not True:
        raise ContractError("every development company must become an E5 exclusion")
    if set(config.get("feature_blocks", {})) != BLOCKS:
        raise ContractError("config must declare exactly V, O, VO, and CC")

    for block, declaration in config["feature_blocks"].items():
        expected = list(block_features(schema, block))
        if declaration.get("features") != expected:
            raise ContractError(f"config feature list drifted for block {block}")
        validate_predictor_columns(expected, schema, block)
    eligible = {
        block
        for block, declaration in config["feature_blocks"].items()
        if declaration.get("s0_candidate_eligible") is True
    }
    if eligible != {"V", "VO"}:
        raise ContractError("only V and VO may be S0 candidate feature blocks")
    if config["feature_blocks"]["O"].get("role") != "OBSERVABILITY_ONLY_DIAGNOSTIC":
        raise ContractError("O must remain an observability-only diagnostic")
    if config["feature_blocks"]["CC"].get("role") != "COMPLETE_CASE_SENSITIVITY_ONLY":
        raise ContractError("CC must remain a complete-case sensitivity analysis")

    candidates = config.get("candidate_model_families") or []
    families = [candidate.get("family") for candidate in candidates]
    if set(families) != APPROVED_MODEL_FAMILIES or len(families) != len(
        APPROVED_MODEL_FAMILIES
    ):
        raise ContractError("candidate set must contain exactly the two approved families")
    for candidate in candidates:
        search = candidate.get("search_space")
        if not isinstance(search, dict) or not search:
            raise ContractError(f"finite search space missing for {candidate.get('family')}")
        if any(not isinstance(values, list) or not values for values in search.values()):
            raise ContractError(f"search space must use non-empty finite lists: {candidate['family']}")

    cv = config.get("cross_validation", {})
    if cv.get("group_key") != "company_id" or not cv.get("company_disjoint"):
        raise ContractError("cross-validation must enforce company-level separation")
    preprocessing = config.get("preprocessing", {})
    if preprocessing.get("fit_scope") != "TRAINING_FOLD_ONLY":
        raise ContractError("preprocessing must be fitted inside each training fold")
    for operation in ("imputation", "scaling", "feature_selection"):
        if preprocessing.get(operation, {}).get("fit_scope") != "TRAINING_FOLD_ONLY":
            raise ContractError(f"{operation} is not training-fold isolated")
    if preprocessing.get("imputation", {}).get("automatic_missing_indicators"):
        raise ContractError("implicit missingness indicators would contaminate block V")
    if preprocessing.get("feature_selection", {}).get("policy") != "DISABLED":
        raise ContractError("feature selection is not approved by the v1 contract")

    leakage = config.get("leakage_guards", {})
    if not leakage.get("outcome_fields_forbidden"):
        raise ContractError("outcome-field guard must be enabled")
    if leakage.get("maximum_information_timing") != "PREDICTION_CUTOFF":
        raise ContractError("future-period information guard must be enabled")
    if leakage.get("selection_may_use_e5_cohort_or_outcomes") is not False:
        raise ContractError("candidate selection must be isolated from E5")

    selection = config.get("future_model_selection_rule") or {}
    if selection.get("primary_ranking_metric") != "mean_outer_fold_AUROC":
        raise ContractError("selection primary metric must be mean outer-fold AUROC")
    if selection.get("secondary_ranking_metric") != "mean_outer_fold_PR_AUC":
        raise ContractError("selection secondary metric must be mean outer-fold PR-AUC")
    tie_rule = selection.get("tie_rule")
    if not isinstance(tie_rule, list) or len(tie_rule) < 4:
        raise ContractError("selection must define a deterministic total-order tie rule")

    calibration = config.get("calibration") or {}
    if calibration.get("status") != "UNCALIBRATED":
        raise ContractError("draft reference scores must remain UNCALIBRATED")
    if calibration.get("probability_interpretation_allowed") is not False:
        raise ContractError("uncalibrated scores cannot be interpreted as probabilities")


def _candidate(config: dict[str, Any], family: str) -> dict[str, Any]:
    if family not in APPROVED_MODEL_FAMILIES:
        raise ContractError(f"unauthorized candidate model family: {family}")
    candidates = {
        candidate["family"]: candidate
        for candidate in config.get("candidate_model_families", [])
    }
    if family not in candidates:
        raise ContractError(f"candidate family is not declared: {family}")
    return candidates[family]


def validate_candidate_parameters(
    family: str,
    parameters: dict[str, Any],
    config: dict[str, Any],
) -> None:
    """Reject parameters outside the finite prospective search contract."""

    candidate = _candidate(config, family)
    fixed = candidate.get("fixed_parameters") or {}
    search = candidate.get("search_space") or {}
    allowed_names = set(fixed) | set(search)
    unknown = set(parameters) - allowed_names
    if unknown:
        raise ContractError(f"unknown hyperparameters for {family}: {sorted(unknown)}")
    for name, expected in fixed.items():
        if name not in parameters or parameters[name] != expected:
            raise ContractError(f"fixed hyperparameter mismatch for {family}.{name}")
    for name, allowed_values in search.items():
        if name not in parameters or parameters[name] not in allowed_values:
            raise ContractError(f"hyperparameter outside approved search space: {family}.{name}")


def contract_sha256(
    schema: dict[str, Any],
    config: dict[str, Any],
    manifest_template: dict[str, Any],
    development_data_template: dict[str, Any] | None = None,
) -> str:
    """Hash the prospective design, never a fitted model or an E5 freeze."""

    development_data_template = development_data_template or load_development_data_template()
    return artifact_sha256(
        {
            "artifact_manifest_template_sha256": artifact_sha256(manifest_template),
            "development_data_manifest_template_sha256": artifact_sha256(
                development_data_template
            ),
            "experiment_config_sha256": artifact_sha256(config),
            "feature_schema_sha256": artifact_sha256(schema),
        }
    )


def fitted_artifact_sha256(manifest: dict[str, Any]) -> str:
    """Hash a completed fitted manifest without its self-referential identity field."""

    payload = deepcopy(manifest)
    hashes = payload.get("hashes")
    if not isinstance(hashes, dict) or "fitted_artifact_hash" not in hashes:
        raise ContractError("manifest is missing hashes.fitted_artifact_hash")
    del hashes["fitted_artifact_hash"]
    return artifact_sha256(payload)


def validate_manifest(
    manifest: dict[str, Any],
    schema: dict[str, Any],
    config: dict[str, Any],
) -> None:
    """Validate a draft or future fitted manifest without loading serialized artifacts."""

    validate_config(config, schema)
    if manifest.get("schema_version") != "1":
        raise ContractError("artifact manifest schema_version must be '1'")
    if manifest.get("artifact") != "StrongTabularReference-v1":
        raise ContractError("incorrect artifact identity")
    status = manifest.get("status")
    if status not in {STATUS, "FROZEN"}:
        raise ContractError("artifact status must be DRAFT_NOT_FROZEN or FROZEN")

    feature = manifest.get("feature_contract") or {}
    if feature.get("feature_schema_version") != schema.get("schema_version"):
        raise ContractError("manifest feature schema version mismatch")
    if feature.get("feature_schema_sha256") != artifact_sha256(schema):
        raise ContractError("manifest feature schema hash mismatch")
    candidate_orders = feature.get("candidate_feature_orders") or {}
    if set(candidate_orders) != {"V", "VO"}:
        raise ContractError("manifest must declare explicit V and VO candidate ordering")
    for block, columns in candidate_orders.items():
        validate_predictor_columns(columns, schema, block)
        if list(columns) != list(block_features(schema, block)):
            raise ContractError(f"manifest feature ordering drifted for {block}")

    selected_block = feature.get("selected_feature_block")
    ordered_names = feature.get("ordered_feature_names")
    selected_types = feature.get("selected_feature_types")
    if selected_block != "TO_BE_SELECTED":
        if selected_block not in {"V", "VO"}:
            raise ContractError("selected feature block is not eligible for S0")
        if ordered_names != candidate_orders[selected_block]:
            raise ContractError("selected ordered features do not match the chosen block")
        type_by_name = {
            entry["canonical_name"]: entry["expected_type"] for entry in schema["features"]
        }
        expected_types = [type_by_name[name] for name in ordered_names]
        if selected_types != expected_types:
            raise ContractError("selected feature types do not match the feature schema")
    elif ordered_names != "TO_BE_FITTED" or selected_types != "TO_BE_FITTED":
        raise ContractError("unselected draft features must remain TO_BE_FITTED")

    preprocessing = manifest.get("preprocessing") or {}
    imputation = preprocessing.get("imputation") or {}
    if imputation.get("automatic_missing_indicators") is not False:
        raise ContractError("implicit missingness indicators are forbidden for V")
    if (preprocessing.get("feature_selection") or {}).get("method") != "DISABLED":
        raise ContractError("feature selection is not authorized")

    model = manifest.get("model") or {}
    family = model.get("family")
    if family != "TO_BE_SELECTED":
        parameters = model.get("exact_hyperparameters")
        if not isinstance(parameters, dict):
            raise ContractError("selected model must declare exact hyperparameters")
        validate_candidate_parameters(family, parameters, config)
    elif model.get("exact_hyperparameters") != "TO_BE_FITTED":
        raise ContractError("unselected model parameters must remain TO_BE_FITTED")

    selection = manifest.get("selection") or {}
    if set(selection.get("candidate_family_list") or []) != APPROVED_MODEL_FAMILIES:
        raise ContractError("manifest candidate family list drifted")
    if selection.get("config_sha256") != artifact_sha256(config):
        raise ContractError("manifest experiment-config hash mismatch")

    development = manifest.get("development_data") or {}
    if development.get("proposal_status") != "SUPERSEDED_BY_APPROVED_MANIFEST":
        raise ContractError("artifact template has stale development-data proposal status")
    if development.get("e5_artifacts_referenced") is not False:
        raise ContractError("E5 cohort or outcome artifacts must not be referenced")
    forbidden_payload_keys = {"labels", "outcomes", "outcome_values", "target_values"}
    if forbidden_payload_keys & set(development):
        raise ContractError("outcome values must not be embedded in an artifact manifest")
    development_strings = [value.casefold().replace("\\", "/") for value in _strings(development)]
    if any(
        "research/e5/" in value or "e5_cohort" in value or "e5_outcome" in value
        for value in development_strings
    ):
        raise ContractError("E5 cohort or outcome artifacts must not be referenced")
    if development.get("use_scope") != "DEVELOPMENT_SELECTION_AND_FINAL_DEVELOPMENT_FIT_ONLY":
        raise ContractError("development data use scope is invalid")

    calibration = manifest.get("calibration") or {}
    if calibration.get("status") == "CALIBRATED":
        if not _is_sha256(calibration.get("artifact_sha256")):
            raise ContractError("CALIBRATED status requires calibration artifact provenance")
    elif (
        calibration.get("status") != "UNCALIBRATED"
        or calibration.get("probability_interpretation_allowed") is not False
    ):
        raise ContractError("draft output must remain UNCALIBRATED and non-probabilistic")

    output = manifest.get("output_contract") or {}
    if output.get("final_decision_authority") != "NONE_PREDICTION_ONLY":
        raise ContractError("S0 output cannot authorize a final decision")
    if "not a validated probability" not in output.get("calibration_rule", ""):
        raise ContractError("output contract must distinguish score from probability")

    security = manifest.get("serialization_security") or {}
    if not security.get("hash_verification_before_load"):
        raise ContractError("serialized artifact hashes must be verified before loading")
    if not security.get("untrusted_pickle_or_joblib_load_forbidden"):
        raise ContractError("untrusted serialized artifacts must be rejected")

    hashes = manifest.get("hashes") or {}
    fitted_hash_fields = {
        "fitted_artifact_hash",
        "fitted_model_sha256",
        "fitted_preprocessor_sha256",
        "selection_record_sha256",
        "verification_report_sha256",
    }
    if status == STATUS:
        if any(hashes.get(name) != "TO_BE_FITTED" for name in fitted_hash_fields):
            raise ContractError("draft fitted-artifact fields must remain TO_BE_FITTED")
        if hashes.get("e5_freeze_identity") != "TO_BE_FROZEN":
            raise ContractError("draft E5 freeze identity must remain TO_BE_FROZEN")
    else:
        if any(not _is_sha256(hashes.get(name)) for name in fitted_hash_fields):
            raise ContractError("FROZEN status requires every fitted artifact hash")
        if selected_block not in {"V", "VO"} or family not in APPROVED_MODEL_FAMILIES:
            raise ContractError("FROZEN status requires selected feature and model identities")
        if not _is_sha256(development.get("manifest_sha256")):
            raise ContractError("FROZEN status requires an approved development-data manifest")
        if hashes["fitted_artifact_hash"] != fitted_artifact_sha256(manifest):
            raise ContractError("fitted artifact hash does not match canonical manifest content")


def validate_contract_identity(
    identity: dict[str, Any],
    schema: dict[str, Any],
    config: dict[str, Any],
    manifest_template: dict[str, Any],
) -> None:
    if identity.get("status") != STATUS:
        raise ContractError("contract identity must remain DRAFT_NOT_FROZEN")
    expected = {
        "artifact_manifest_template_sha256": artifact_sha256(manifest_template),
        "development_data_manifest_template_sha256": artifact_sha256(
            load_development_data_template()
        ),
        "experiment_config_sha256": artifact_sha256(config),
        "feature_schema_sha256": artifact_sha256(schema),
    }
    if identity.get("components") != expected:
        raise ContractError("contract identity component hash drift")
    if identity.get("contract_sha256") != contract_sha256(schema, config, manifest_template):
        raise ContractError("contract hash drift")
    if identity.get("fitted_artifact_hash") != "TO_BE_FITTED":
        raise ContractError("fitted artifact hash must not exist in the draft contract")
    if identity.get("e5_freeze_identity") != "TO_BE_FROZEN":
        raise ContractError("E5 freeze identity must not exist in the draft contract")


def main() -> int:
    schema = load_schema()
    config = load_config()
    manifest = load_manifest_template()
    identity = load_contract_identity()
    validate_config(config, schema)
    validate_manifest(manifest, schema, config)
    validate_contract_identity(identity, schema, config, manifest)
    print(
        json.dumps(
            {
                "status": STATUS,
                "contract_sha256": contract_sha256(schema, config, manifest),
                "schema_sha256": artifact_sha256(schema),
                "config_sha256": artifact_sha256(config),
                "manifest_template_sha256": artifact_sha256(manifest),
                "development_data_manifest_template_sha256": artifact_sha256(
                    load_development_data_template()
                ),
                "fitted_artifact_hash": "TO_BE_FITTED",
                "e5_freeze_identity": "TO_BE_FROZEN",
                "feature_counts": {
                    block: len(block_features(schema, block)) for block in sorted(BLOCKS)
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
