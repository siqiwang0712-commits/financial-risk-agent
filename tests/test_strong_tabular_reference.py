from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import e4r_data
import pytest
from finrisk.reproducibility import verify_frozen_experiment

from research.strong_tabular_reference import contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def schema() -> dict:
    payload = contract.load_schema()
    contract.validate_schema(payload)
    return payload


@pytest.fixture(scope="module")
def config(schema: dict) -> dict:
    payload = contract.load_config()
    contract.validate_config(payload, schema)
    return payload


@pytest.fixture(scope="module")
def manifest(schema: dict, config: dict) -> dict:
    payload = contract.load_manifest_template()
    contract.validate_manifest(payload, schema, config)
    return payload


def test_feature_families_are_exclusive_and_valid(schema: dict) -> None:
    names = [feature["canonical_name"] for feature in schema["features"]]
    assert len(names) == len(set(names))
    assert {feature["classification"] for feature in schema["features"]} == {
        "FINANCIAL_VALUE",
        "TEMPORAL_FINANCIAL",
        "OBSERVABILITY",
    }
    for feature in schema["features"]:
        assert isinstance(feature["classification"], str)
        assert feature["outcome_role"] == "NONE"


def test_observability_and_value_blocks_do_not_cross(schema: dict) -> None:
    by_name = {feature["canonical_name"]: feature for feature in schema["features"]}
    value = set(contract.block_features(schema, "V"))
    observability = set(contract.block_features(schema, "O"))
    combined = set(contract.block_features(schema, "VO"))
    complete_case = set(contract.block_features(schema, "CC"))

    assert value and observability and value.isdisjoint(observability)
    assert combined == value | observability
    assert complete_case == value
    assert all(by_name[name]["classification"] != "OBSERVABILITY" for name in value)
    assert all(by_name[name]["classification"] == "OBSERVABILITY" for name in observability)


def test_outcome_field_cannot_enter_the_contract(schema: dict) -> None:
    corrupted = copy.deepcopy(schema)
    injected = copy.deepcopy(corrupted["features"][0])
    injected["canonical_name"] = "financial_deterioration_12m"
    corrupted["features"].append(injected)
    with pytest.raises(contract.ContractError, match="outcome-derived"):
        contract.validate_schema(corrupted)

    with pytest.raises(contract.ContractError, match="outcome field"):
        contract.validate_predictor_columns(["label"], schema, "V")


def test_future_period_field_cannot_enter_the_contract(schema: dict) -> None:
    corrupted = copy.deepcopy(schema)
    injected = copy.deepcopy(corrupted["features"][0])
    injected["canonical_name"] = "future_revenue"
    injected["information_timing"] = "AFTER_PREDICTION_CUTOFF"
    corrupted["features"].append(injected)
    with pytest.raises(contract.ContractError, match="future or unknown-period"):
        contract.validate_schema(corrupted)


def test_config_is_draft_hash_bound_and_deterministic(schema: dict, config: dict) -> None:
    assert config["status"] == "DRAFT_NOT_FROZEN"
    assert config["feature_schema_sha256"] == contract.artifact_sha256(schema)
    assert contract.artifact_sha256(schema) == contract.artifact_sha256(
        contract.load_schema()
    )
    assert contract.artifact_sha256(config) == contract.artifact_sha256(
        contract.load_config()
    )

    drifted = copy.deepcopy(config)
    drifted["feature_schema_sha256"] = "0" * 64
    with pytest.raises(contract.ContractError, match="schema hash"):
        contract.validate_config(drifted, schema)


def test_draft_manifest_and_contract_identity_validate(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    identity = contract.load_contract_identity()
    contract.validate_contract_identity(identity, schema, config, manifest)
    assert manifest["status"] == "DRAFT_NOT_FROZEN"
    assert identity["fitted_artifact_hash"] == "TO_BE_FITTED"
    assert identity["e5_freeze_identity"] == "TO_BE_FROZEN"


def test_contract_hash_is_canonical_and_key_order_independent(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    expected = contract.contract_sha256(schema, config, manifest)
    reordered = dict(reversed(list(manifest.items())))
    assert contract.contract_sha256(schema, config, reordered) == expected
    assert contract.load_contract_identity()["contract_sha256"] == expected


def test_future_fitted_hash_rule_is_non_self_referential(manifest: dict) -> None:
    first = copy.deepcopy(manifest)
    second = copy.deepcopy(manifest)
    first["hashes"]["fitted_artifact_hash"] = "first-placeholder"
    second["hashes"]["fitted_artifact_hash"] = "second-placeholder"
    assert contract.fitted_artifact_sha256(first) == contract.fitted_artifact_sha256(second)


def test_manifest_rejects_unknown_and_cross_family_features(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    unknown = copy.deepcopy(manifest)
    unknown["feature_contract"]["candidate_feature_orders"]["V"][0] = "unknown_ratio"
    with pytest.raises(contract.ContractError, match="not registered"):
        contract.validate_manifest(unknown, schema, config)

    observed_in_v = copy.deepcopy(manifest)
    observed_in_v["feature_contract"]["candidate_feature_orders"]["V"][0] = (
        "observed__current_ratio"
    )
    with pytest.raises(contract.ContractError, match="not registered for block V"):
        contract.validate_manifest(observed_in_v, schema, config)

    value_in_o = copy.deepcopy(manifest)
    value_in_o["feature_contract"]["candidate_feature_orders"]["O"] = ["current_ratio"]
    with pytest.raises(contract.ContractError, match="explicit V and VO"):
        contract.validate_manifest(value_in_o, schema, config)


def test_manifest_rejects_future_period_schema(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    future = copy.deepcopy(schema)
    future["features"][0]["information_timing"] = "AFTER_PREDICTION_CUTOFF"
    with pytest.raises(contract.ContractError, match="future or unknown-period"):
        contract.validate_manifest(manifest, future, config)


def test_manifest_rejects_outcome_field_in_feature_order(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    corrupted = copy.deepcopy(manifest)
    corrupted["feature_contract"]["candidate_feature_orders"]["V"][0] = "label"
    with pytest.raises(contract.ContractError, match="outcome field"):
        contract.validate_manifest(corrupted, schema, config)


def test_manifest_rejects_implicit_indicators_in_v(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    corrupted = copy.deepcopy(manifest)
    corrupted["preprocessing"]["imputation"]["automatic_missing_indicators"] = True
    with pytest.raises(contract.ContractError, match="implicit missingness"):
        contract.validate_manifest(corrupted, schema, config)


def test_candidate_family_and_grid_are_closed(config: dict) -> None:
    logistic = {
        "C": 1.0,
        "class_weight": "NONE",
        "max_iter": 5000,
        "penalty": "l2",
        "solver": "lbfgs",
    }
    contract.validate_candidate_parameters("logistic_regression", logistic, config)

    with pytest.raises(contract.ContractError, match="unauthorized"):
        contract.validate_candidate_parameters("xgboost", {}, config)

    outside = dict(logistic, C=1000.0)
    with pytest.raises(contract.ContractError, match="outside approved search space"):
        contract.validate_candidate_parameters("logistic_regression", outside, config)


def test_manifest_rejects_false_calibration_and_freeze(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    calibrated = copy.deepcopy(manifest)
    calibrated["calibration"]["status"] = "CALIBRATED"
    calibrated["calibration"]["probability_interpretation_allowed"] = True
    with pytest.raises(contract.ContractError, match="calibration artifact provenance"):
        contract.validate_manifest(calibrated, schema, config)

    frozen = copy.deepcopy(manifest)
    frozen["status"] = "FROZEN"
    with pytest.raises(contract.ContractError, match="requires every fitted artifact hash"):
        contract.validate_manifest(frozen, schema, config)


def test_manifest_rejects_e5_artifact_reference(
    schema: dict,
    config: dict,
    manifest: dict,
) -> None:
    corrupted = copy.deepcopy(manifest)
    corrupted["development_data"]["e5_artifacts_referenced"] = True
    with pytest.raises(contract.ContractError, match="E5 cohort or outcome"):
        contract.validate_manifest(corrupted, schema, config)

    embedded = copy.deepcopy(manifest)
    embedded["development_data"]["outcome_values"] = [0, 1]
    with pytest.raises(contract.ContractError, match="outcome values"):
        contract.validate_manifest(embedded, schema, config)


def test_preprocessing_and_company_separation_guards_are_explicit(config: dict) -> None:
    assert config["cross_validation"]["company_disjoint"] is True
    assert config["cross_validation"]["group_key"] == "company_id"
    for name in ("imputation", "scaling", "feature_selection"):
        assert config["preprocessing"][name]["fit_scope"] == "TRAINING_FOLD_ONLY"
    assert config["preprocessing"]["imputation"]["automatic_missing_indicators"] is False
    assert config["leakage_guards"]["outcome_fields_forbidden"] is True
    assert config["leakage_guards"]["future_period_fields_forbidden"] is True


def test_readiness_json_uses_only_the_declared_status_vocabulary() -> None:
    path = ROOT / "research/e5_readiness/readiness.json"
    readiness = json.loads(path.read_text(encoding="utf-8"))
    assert readiness["status"] == "BLOCKED"
    assert readiness["study"] == "E5"
    statuses = {area["status"] for area in readiness["areas"].values()}
    assert statuses <= {"READY", "PARTIAL", "BLOCKED", "NOT_APPLICABLE"}
    assert readiness["evidence_boundary"]["e5"] == "NOT_RUN_NOT_FROZEN"


@pytest.mark.parametrize(
    "experiment_id", ["v0.3.1-E1-diagnostic", "v0.3.1-E2", "v0.3.1-E3"]
)
def test_frozen_e1_e3_forensic_artifacts_remain_verified(experiment_id: str) -> None:
    directory = ROOT / "research/results/v0.3.1/benchmark_forensics" / experiment_id
    report = verify_frozen_experiment(directory, ROOT)
    assert report["artifact_integrity"] == "VERIFIED"
    assert report["writes_performed"] is False


def test_frozen_e4_artifacts_remain_verified() -> None:
    report = e4r_data.verify_sources(run_external=False)
    assert report.status == "PASS", report.failures
    assert report.e4_frozen_files
    assert all(entry["status"] == "PASS" for entry in report.e4_frozen_files)

    path = ROOT / "scripts/verify_e4_public_artifacts.py"
    spec = importlib.util.spec_from_file_location("verify_e4_public_artifacts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.verify()["status"] == "PASS"
