from __future__ import annotations

import json
from pathlib import Path

import pytest
from finrisk.e4_agent import (
    AgentSchemaError,
    _parse,
    build_manifest,
    execute_batch,
    hybrid_predictions,
    make_batches,
    packet,
    replay_frozen_agent,
    validate_agent_url,
)
from finrisk.e4_core import (
    FEATURE_ARCHIVES,
    OUTCOME_ARCHIVES,
    SOURCE_COMMIT,
    SOURCE_TAG,
    Stage,
    StudyState,
    _stratified_sample,
    canonical_bytes,
    canonical_hash,
    verify_previous_270,
    write_json,
)
from finrisk.e4_evaluation import (
    _select_concordance_candidate,
    assemble_analysis,
    paired_rows,
    positive_improvement_claim_allowed,
)


def feature(index: int = 1) -> dict:
    return {
        "observation_id": f"E4_OBS_{index:06d}",
        "masked_company_id": f"E4_COMPANY_{index:06d}",
        "cik": f"{index:010d}",
        "accession": f"{index:010d}-24-000001",
        "sic": 3571,
        "sector": "Manufacturing",
        "current": {
            "revenue": 100.0,
            "net_income": 5.0,
            "total_assets": 200.0,
            "total_liabilities": 80.0,
            "current_assets": 60.0,
            "current_liabilities": 50.0,
            "operating_cash_flow": 8.0,
            "capital_expenditure": 2.0,
            "total_debt": 40.0,
        },
        "previous": {
            "revenue": 90.0,
            "net_income": 4.0,
            "total_assets": 180.0,
            "total_liabilities": 75.0,
            "current_assets": 55.0,
            "current_liabilities": 48.0,
            "operating_cash_flow": 7.0,
            "capital_expenditure": 2.0,
            "total_debt": 35.0,
        },
        "metrics": {"current_ratio": 1.2, "revenue_growth": 0.111, "net_margin": 0.05},
    }


def prediction(row: dict, model_id: str, score: float | None) -> dict:
    return {
        "observation_id": row["observation_id"],
        "masked_company_id": row["masked_company_id"],
        "model_id": model_id,
        "score": score,
        "prediction": None if score is None else int(score >= 0.5),
        "coverage": 0 if score is None else 1,
        "abstained": score is None,
        "reason_codes": [],
        "input_hash": "a" * 64,
        "config_hash": "b" * 64,
    }


def test_source_identity_is_frozen() -> None:
    assert SOURCE_TAG == "v0.3.4"
    assert SOURCE_COMMIT == "4273b070678240fe7cbdf01a17527afcc71c500e"


def test_feature_and_outcome_archives_are_disjoint() -> None:
    assert set(FEATURE_ARCHIVES).isdisjoint(OUTCOME_ARCHIVES)


def test_previous_270_rejects_an_invented_list(tmp_path: Path) -> None:
    path = tmp_path / "previous.json"
    path.write_text(json.dumps([{"cik": "1"}] * 270), encoding="utf-8")
    with pytest.raises(RuntimeError, match="exact frozen"):
        verify_previous_270(path)


def test_cohort_sampling_is_deterministic() -> None:
    rows = [{"cik": f"{index:010d}", "sector": "Manufacturing" if index % 2 else "Retail"} for index in range(2100)]
    assert _stratified_sample(rows) == _stratified_sample(list(reversed(rows)))
    assert len(_stratified_sample(rows)) == 2000


def test_cohort_sampling_has_no_outcome_argument() -> None:
    assert _stratified_sample.__code__.co_varnames[:2] == ("rows", "limit")


@pytest.mark.parametrize("url", ["https://localhost:8080", "http://example.com", "http://8.8.8.8:8080"])
def test_local_agent_rejects_nonlocal_contract(url: str) -> None:
    with pytest.raises(RuntimeError, match="localhost"):
        validate_agent_url(url)


@pytest.mark.parametrize("url", ["http://localhost:8080", "http://127.0.0.1:8080", "http://finrisk-e4-agent-api:8080"])
def test_local_agent_accepts_only_declared_local_hosts(url: str) -> None:
    validate_agent_url(url)


def test_agent_identity_is_masked() -> None:
    value = packet(feature(), "A2")
    encoded = json.dumps(value)
    assert "cik" not in encoded.lower()
    assert "accession" not in encoded.lower()
    assert value["case_id"].startswith("E4_COMPANY_")


def test_a0_a1_a2_input_separation() -> None:
    row = feature()
    a0, a1, a2 = (packet(row, name) for name in ("A0", "A1", "A2"))
    assert "raw_fy2024" in a0 and "engineered_features" not in a0
    assert "engineered_features" in a1 and "raw_fy2024" not in a1
    assert {"raw_fy2024", "engineered_features", "traditional_model_outputs"} <= set(a2)


def test_agent_payload_has_no_outcome_or_final_deterministic_scores() -> None:
    encoded = json.dumps(packet(feature(), "A2"))
    for forbidden in ('"outcome"', '"label"', '"B0"', '"B2"', '"B6"'):
        assert forbidden not in encoded


def test_batching_is_deterministic_and_under_budget() -> None:
    rows = [feature(index) for index in range(1, 8)]
    first = make_batches(rows, "A0")
    second = make_batches(list(reversed(rows)), "A0")
    assert first == second
    assert all(batch["estimated_input_tokens"] <= 2867 for batch in first)


def test_batch_manifest_freezes_packet_and_prompt_hashes() -> None:
    value = build_manifest([feature()])
    assert value["prompt_hashes"]["A2"]
    assert all(batch["packet_hashes"] for batch in value["batches"])


def test_batch_id_equality_is_enforced() -> None:
    response = {"choices": [{"message": {"content": json.dumps({"cases": [{"case_id": "WRONG", "risk_score": 0.5, "reason_codes": [], "summary": "x"}]})}}]}
    with pytest.raises(ValueError, match="exactly match"):
        _parse(response, ["E4_COMPANY_000001"])


def test_deterministic_bisect_recovers_without_prompt_change() -> None:
    calls = []

    def transport(_url: str, request: dict) -> dict:
        case_ids = [row["case_id"] for row in json.loads(request["messages"][1]["content"])["cases"]]
        calls.append((case_ids, canonical_hash(request["messages"])))
        if len(case_ids) > 1:
            raise OSError("batch failure")
        content = {"cases": [{"case_id": case_ids[0], "risk_score": 0.5, "reason_codes": ["TEST"], "summary": "ok"}]}
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    rows = [feature(1), feature(2)]
    batch = make_batches(rows, "A0")[0]
    result = execute_batch(batch, "http://localhost:8080", transport)
    assert sorted(row["case_id"] for row in result.cases) == sorted(batch["case_ids"])
    assert not result.failures
    assert calls[0][0] == calls[1][0]


def test_h0_exact_formula() -> None:
    row = feature()
    values = hybrid_predictions([prediction(row, "B6", 0.2)], [prediction(row, "A2", 0.8)], "c" * 64)
    assert values[0]["score"] == 0.5


def test_review_and_insufficient_are_never_labels() -> None:
    row = feature()
    labels = [
        {"observation_id": row["observation_id"], "label_status": "REQUIRES_HUMAN_REVIEW", "financial_deterioration_12m": None}
    ]
    assert assemble_analysis([row], [prediction(row, "B0", 0.5)], labels) == []


def test_paired_comparison_uses_identical_companies() -> None:
    one, two = feature(1), feature(2)
    rows = [
        {**prediction(one, "B0", 0.1), "label": 0, "sector": "M"},
        {**prediction(one, "B6", 0.2), "label": 0, "sector": "M"},
        {**prediction(two, "B6", 0.9), "label": 1, "sector": "M"},
    ]
    paired = paired_rows(rows, "B6", "B0")
    assert [row["observation_id"] for row in paired] == [one["observation_id"]]


def test_frozen_artifact_overwrite_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "frozen.json"
    write_json(path, {"x": 1}, frozen=True)
    with pytest.raises(RuntimeError, match="overwrite"):
        write_json(path, {"x": 2}, frozen=True)


def test_state_machine_rejects_illegal_transition(tmp_path: Path) -> None:
    study = StudyState(tmp_path)
    with pytest.raises(RuntimeError, match="illegal"):
        study.advance(Stage.INPUTS_VERIFIED, Stage.LOCAL_AGENT_VERIFIED, {})


def test_state_machine_does_not_allow_skips(tmp_path: Path) -> None:
    study = StudyState(tmp_path)
    with pytest.raises(RuntimeError, match="exactly one"):
        study.advance(Stage.INIT, Stage.PROTOCOL_FROZEN, {})


def test_canonical_replay_is_byte_identical() -> None:
    left = {"b": [2, 1], "a": 1}
    right = {"a": 1, "b": [2, 1]}
    assert canonical_bytes(left) == canonical_bytes(right)


def test_agent_response_replay_is_deterministic() -> None:
    content = {"cases": [{"case_id": "E4_COMPANY_000001", "risk_score": 0.2, "reason_codes": ["A"], "summary": "x"}]}
    response = {"choices": [{"message": {"content": json.dumps(content)}}]}
    assert _parse(response, ["E4_COMPANY_000001"]) == _parse(response, ["E4_COMPANY_000001"])


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("not-json", "MALFORMED_JSON"),
        (json.dumps({"cases": []}), "CASE_ID_MISMATCH"),
        (json.dumps({"cases": [{"case_id": "E4_COMPANY_000001", "risk_score": 2, "reason_codes": [], "summary": "x"}]}), "SCORE_OUT_OF_RANGE"),
    ],
)
def test_agent_schema_failures_are_machine_classified(content: str, code: str) -> None:
    response = {"choices": [{"message": {"content": content}}]}
    with pytest.raises(AgentSchemaError) as caught:
        _parse(response, ["E4_COMPANY_000001"])
    assert caught.value.code == code


def test_schema_failure_retains_response_for_diagnosis() -> None:
    row = feature()
    batch = make_batches([row], "A0")[0]
    invalid = {"choices": [{"message": {"content": "not-json"}}]}
    result = execute_batch(batch, "http://127.0.0.1:8080", transport=lambda _url, _body: invalid)
    assert result.failures[0]["error"] == "MALFORMED_JSON"
    assert all(record["error_code"] == "MALFORMED_JSON" for record in result.raw)
    assert all(record["response"] == invalid for record in result.raw)


def test_frozen_agent_response_rebuilds_prediction() -> None:
    row = feature()
    manifest = build_manifest([row])
    content = {"cases": [{"case_id": row["masked_company_id"], "risk_score": 0.2, "reason_codes": ["A"], "summary": "x"}]}
    raw = {
        "raw_runs": [
            {"batch_id": batch["batch_id"], "records": [{"response": {"choices": [{"message": {"content": json.dumps(content)}}]}}]}
            for batch in manifest["batches"]
        ],
        "failures": [],
    }
    replay = replay_frozen_agent([row], manifest, raw, "c" * 64)
    assert len(replay) == 3
    assert {item["model_id"] for item in replay} == {"A0", "A1", "A2"}
    assert all(item["score"] == 0.2 for item in replay)


def test_readme_positive_claim_gate_requires_ci_and_adjusted_inference() -> None:
    assert positive_improvement_claim_allowed({"ci_low": 0.01, "holm_adjusted_p": 0.049})
    assert not positive_improvement_claim_allowed({"ci_low": -0.01, "holm_adjusted_p": 0.01})
    assert not positive_improvement_claim_allowed({"ci_low": 0.01, "holm_adjusted_p": 0.05})


def test_feature_and_outcome_archive_names_are_disjoint() -> None:
    assert set(FEATURE_ARCHIVES).isdisjoint(OUTCOME_ARCHIVES)


def test_concordance_duplicate_resolution_rejects_conflicting_values() -> None:
    same = [{"value": "10", "quality": "reported"}, {"value": "10.0", "quality": "reported"}]
    conflict = [{"value": "10", "quality": "reported"}, {"value": "11", "quality": "reported"}]
    assert _select_concordance_candidate(same) is not None
    assert _select_concordance_candidate(conflict) is None
