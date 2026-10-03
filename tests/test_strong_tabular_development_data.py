from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research.strong_tabular_reference import contract
from research.strong_tabular_reference import development_data as data_contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def schema() -> dict:
    return contract.load_schema()


@pytest.fixture(scope="module")
def template(schema: dict) -> dict:
    value = data_contract.load_template()
    data_contract.validate_development_data_manifest(value, schema=schema)
    return value


@pytest.fixture(scope="module")
def proposal(schema: dict) -> dict:
    value = data_contract.load_proposal()
    data_contract.validate_development_data_manifest(value, schema=schema)
    return value


def test_template_is_a_valid_unresolved_draft(template: dict) -> None:
    assert template["status"] == "DRAFT_NOT_FROZEN"
    assert template["dataset_id"] == "TO_BE_NOMINATED"


def test_proposal_is_valid_but_not_approved(proposal: dict) -> None:
    assert proposal["status"] == "PROPOSED_NOT_APPROVED"
    assert proposal["isolation"]["historical_research_exposure"] == "DESIGN_EXPOSED"


def test_invalid_status_is_rejected(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["status"] = "FROZEN"
    with pytest.raises(data_contract.DevelopmentDataError, match="invalid.*status"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_e5_outcome_reference_is_rejected(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["provenance"]["source_files"].append("research/e5/e5_outcomes.json")
    with pytest.raises(data_contract.DevelopmentDataError, match="E5 outcome"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_future_feature_period_is_rejected(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["temporal_contract"]["feature_end"] = "2026-12-31"
    with pytest.raises(data_contract.DevelopmentDataError, match="before outcome"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_missing_endpoint_identity_is_rejected(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["endpoint"]["version"] = ""
    with pytest.raises(data_contract.DevelopmentDataError, match="endpoint name and version"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_company_grouping_omission_is_rejected(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["isolation"]["same_company_rows_must_remain_grouped"] = False
    with pytest.raises(data_contract.DevelopmentDataError, match="company grouping"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_false_approval_with_unresolved_hashes_is_rejected(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["status"] = "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT"
    with pytest.raises(data_contract.DevelopmentDataError, match="unresolved required fields"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_unresolved_source_hash_cannot_be_marked_verified(
    schema: dict, proposal: dict
) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["provenance"]["hash_verification_status"] = "VERIFIED"
    corrupted["provenance"]["source_artifact_hashes"]["cohort.json"] = "TO_BE_VERIFIED"
    with pytest.raises(data_contract.DevelopmentDataError, match="unresolved source hash"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_synthetic_fixture_cannot_be_primary_empirical_data(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["population"]["synthetic_only"] = True
    with pytest.raises(data_contract.DevelopmentDataError, match="synthetic-only"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_feature_schema_hash_mismatch_is_rejected(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["feature_contract"]["feature_schema_sha256"] = "0" * 64
    with pytest.raises(data_contract.DevelopmentDataError, match="feature-schema hash"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_incompatible_endpoint_cannot_be_approved(schema: dict, proposal: dict) -> None:
    corrupted = copy.deepcopy(proposal)
    corrupted["status"] = "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT"
    corrupted["endpoint"]["compatibility_status"] = "NOT_COMPATIBLE"
    with pytest.raises(data_contract.DevelopmentDataError, match="endpoint cannot be approved"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_every_development_company_becomes_e5_exclusion(schema: dict, proposal: dict) -> None:
    assert proposal["isolation"]["e5_future_exclusion_obligation"] is True
    assert "ALL_2000" in proposal["isolation"]["e5_exclusion_scope"]
    corrupted = copy.deepcopy(proposal)
    corrupted["isolation"]["e5_future_exclusion_obligation"] = False
    with pytest.raises(data_contract.DevelopmentDataError, match="E5 exclusion"):
        data_contract.validate_development_data_manifest(corrupted, schema=schema)


def test_canonical_hash_is_deterministic_and_key_order_independent(proposal: dict) -> None:
    expected = data_contract.canonical_manifest_sha256(proposal)
    reordered = dict(reversed(list(proposal.items())))
    assert data_contract.canonical_manifest_sha256(reordered) == expected
    assert data_contract.canonical_manifest_sha256(proposal) == expected


def test_data_contract_does_not_embed_model_artifacts(
    template: dict, proposal: dict
) -> None:
    for payload in (template, proposal):
        assert not ({"model", "predictions", "fitted_model", "cv_results"} & set(payload))
    artifacts = ROOT / "research/strong_tabular_reference/artifacts"
    assert (artifacts / "model.pkl").is_file()
    assert (artifacts / "preprocessor.pkl").is_file()
    assert not [
        path
        for path in (ROOT / "research/strong_tabular_reference").rglob("*")
        if path.is_file()
        and path.suffix.casefold() in {".joblib", ".pkl", ".pickle", ".onnx"}
        and path.parent != artifacts
    ]


def test_json_key_order_does_not_change_loaded_meaning(proposal: dict) -> None:
    encoded = json.dumps(dict(reversed(list(proposal.items()))), sort_keys=False)
    assert json.loads(encoded) == proposal
