import logging
from pathlib import Path

import pytest
from finrisk.agent import FinancialRiskAgent
from finrisk.benchmark_protocol import (
    adjudicate_label,
    calibration_curve,
    fit_decision_stump,
    fit_logistic_baseline,
    inter_rater_agreement,
    predict_logistic,
    selective_metrics,
    validate_company_year_manifest,
)
from finrisk.domain import Evidence
from finrisk.enterprise.decision import (
    build_decision_trace,
    canonical_hash,
    create_snapshot,
    replay_diff,
    replay_snapshot,
)
from finrisk.enterprise.domain import (
    AnalysisSnapshot,
    ModelRecord,
    Principal,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
    Role,
    new_id,
)
from finrisk.enterprise.fusion import (
    failure_aware_decision,
    hierarchical_escalation,
    sensitivity_analysis,
)
from finrisk.enterprise.governance import (
    champion_challenger,
    drift_report,
    transition_model,
)
from finrisk.enterprise.observability import (
    bind_correlation_id,
    structured_event,
    traced_stage,
)
from finrisk.enterprise.security import CredentialStore, issue_api_key
from finrisk.enterprise.service import EnterpriseRiskService
from finrisk.evidence import EvidenceVerifier

ROOT = Path(__file__).resolve().parents[1]


def test_migration_contains_decision_grade_and_immutable_audit_controls():
    sql = (ROOT / "migrations" / "001_enterprise_core.sql").read_text(encoding="utf-8")
    for table in (
        "analysis_snapshots",
        "validation_records",
        "risk_cases",
        "audit_events",
    ):
        assert f"{table}" in sql
    assert "audit_events_immutable" in sql and "reject_audit_mutation" in sql
    temporal_sql = (ROOT / "migrations" / "002_temporal_intelligence.sql").read_text(
        encoding="utf-8"
    )
    assert "risk_snapshots" in temporal_sql and "decision_bundles" in temporal_sql
    assert "temporal_evidence_edges" in temporal_sql


def test_decision_trace_snapshot_replay_and_tenant_isolation():
    assessment = {
        "confidence": 0.8,
        "dimensions": {
            "liquidity": {"score": 75, "coverage": 1, "key_drivers": ["LIQ_1"]}
        },
        "triggered_rules": [
            {
                "rule_id": "LIQ_1",
                "family": "liquidity",
                "source_refs": [
                    {
                        "document": "10-K",
                        "page": 8,
                        "source_text": "Cash declined",
                        "verification_status": "verified",
                    }
                ],
            }
        ],
    }
    fusion = {
        "method": "hierarchical_escalation",
        "drivers": ["liquidity"],
        "disagreement": 0.1,
        "decision": "FLAG",
    }
    trace = build_decision_trace(assessment, fusion, {"rules": "r1", "fusion": "f1"})
    assert trace["proof_coverage"] == 1 and trace["paths"][0]["reason_code"] == "LIQ_1"
    snapshot = create_snapshot(
        "org-a",
        "entity",
        {"cash": 1},
        {"decision": "FLAG"},
        {"10-K": "d1"},
        {"rules": "r1"},
    )
    assert replay_diff(snapshot, {"decision": "FLAG"})["classification"] == "IDENTICAL"
    assert (
        replay_diff(snapshot, {"decision": "PASS"})["classification"]
        == "DRIFT_DETECTED"
    )
    assert (
        replay_snapshot(snapshot, lambda frozen: {"decision": "FLAG"}, {"rules": "r1"})[
            "status"
        ]
        == "REPLAYED"
    )
    assert (
        replay_snapshot(snapshot, lambda frozen: {}, {"rules": "r2"})["status"]
        == "VERSION_MISMATCH"
    )
    service = EnterpriseRiskService()
    service.repository.save(snapshot)
    with pytest.raises(ValueError, match="already exists"):
        service.repository.save(snapshot)
    assert (
        service.repository.get_snapshot("org-a", snapshot.id).input_hash
        == snapshot.input_hash
    )
    with pytest.raises(KeyError):
        service.repository.get_snapshot("org-b", snapshot.id)


def test_located_or_noncontiguous_evidence_never_verifies_material_path():
    evidence = Evidence("10-K", 1, "cash declined debt increased liquidity weak", 2025)
    page = {1: "Cash declined. Unrelated discussion. Debt increased. Much later liquidity weak."}
    checked = EvidenceVerifier().verify(evidence, page)
    assert checked.verification_status == "unverified" and not checked.verified
    assessment = {
        "dimensions": {"liquidity": {"key_drivers": ["L1"], "coverage": .5}},
        "triggered_rules": [{"rule_id": "L1", "family": "liquidity", "source_refs": [
            {"verification_status": "verified"}, {"verification_status": "located"}
        ]}],
    }
    trace = build_decision_trace(assessment, {"decision": "FLAG"})
    assert trace["paths"][0]["evidence_path_status"] == "UNVERIFIED"


def test_snapshot_detaches_mutable_inputs_and_preserves_hash():
    original_input = {"facts": {"cash": 1}}
    original_output = {"decision": "FLAG", "items": [1]}
    snapshot = create_snapshot("org", "entity", original_input, original_output, {}, {})
    original_input["facts"]["cash"] = 999
    original_output["items"].append(2)
    assert snapshot.frozen_input["facts"]["cash"] == 1
    assert snapshot.frozen_output["items"] == [1]
    assert canonical_hash(snapshot.frozen_input) == snapshot.input_hash
    assert canonical_hash(snapshot.frozen_output) == snapshot.output_hash


def test_risk_case_rejects_same_tenant_cross_entity_snapshot():
    service = EnterpriseRiskService()
    org = service.create_organization("Org", "analyst")
    principal = Principal("analyst", org.id, Role.ANALYST)
    first = service.create_entity(principal, "First")
    second = service.create_entity(principal, "Second")
    snapshot = create_snapshot(
        org.id, first.id, {"cash": 1}, {"agent": {}}, {}, {"fusion": "v1"}
    )
    service.save_snapshot(principal, snapshot)
    case = RiskCase(
        new_id("case"), org.id, second.id, RiskDomain.LIQUIDITY,
        "high", "stable", 0.5, 0.5, snapshot_id=snapshot.id,
    )
    with pytest.raises(ValueError, match="snapshot entity"):
        service.create_case(principal, case)


def test_failure_policy_sensitivity_and_final_case_proof_gate():
    result = hierarchical_escalation({"liquidity": 70, "cash_flow": 30}, 0.8, 0.8)
    assert (
        failure_aware_decision(result, {"parser_failure": True})["decision"]
        == "ABSTAIN"
    )
    assert (
        failure_aware_decision(result, {"llm_unavailable": True})["decision"]
        == "REVIEW"
    )
    assert sensitivity_analysis({"liquidity": 70, "cash_flow": 30}, result)
    strict = hierarchical_escalation({"liquidity": 55}, 0.8, 0.8, {"flag_score": 50})
    assert strict.decision == "FLAG"
    service = EnterpriseRiskService()
    org = service.create_organization("Org", "a")
    analyst = Principal("a", org.id, Role.ANALYST)
    reviewer = Principal("r", org.id, Role.REVIEWER)
    entity = service.create_entity(analyst, "Entity")
    case = RiskCase(
        new_id("case"),
        org.id,
        entity.id,
        RiskDomain.LIQUIDITY,
        "high",
        "stable",
        0.8,
        0.8,
    )
    service.create_case(analyst, case)
    other_org = service.create_organization("Other", "x")
    with pytest.raises(KeyError):
        service.create_case(
            Principal("x", other_org.id, Role.ANALYST),
            RiskCase(
                new_id("case"),
                other_org.id,
                entity.id,
                RiskDomain.LIQUIDITY,
                "high",
                "stable",
                0.8,
                0.8,
            ),
        )
    service.transition(reviewer, case.id, RiskCaseStatus.OPEN)
    service.transition(reviewer, case.id, RiskCaseStatus.UNDER_REVIEW)
    with pytest.raises(ValueError, match="server-side analysis snapshot"):
        service.transition(reviewer, case.id, RiskCaseStatus.ACCEPTED)


def test_credential_rotation_prevents_header_role_impersonation():
    store = CredentialStore()
    raw, credential = issue_api_key("org", "viewer", Role.VIEWER)
    store.register(credential)
    assert store.authenticate(raw).role == Role.VIEWER
    replacement_raw, replacement = store.rotate(credential.id)
    with pytest.raises(PermissionError):
        store.authenticate(raw)
    assert store.authenticate(replacement_raw).organization_id == "org"
    assert replacement.id != credential.id


def test_governance_requires_validation_and_reports_drift():
    record = ModelRecord(
        "m", "o", "fusion", "1", "owner", "risk fusion", "not calibrated"
    )
    with pytest.raises(ValueError):
        transition_model(record, "approved")
    validated = transition_model(record, "validated", "validation-1")
    assert (
        transition_model(validated, "approved", "validation-1").deployment_state
        == "approved"
    )
    assert (
        champion_challenger([0.8, 0.2], [0.9, 0.1], [1, 0])["recommendation"]
        == "PROMOTE_CHALLENGER"
    )
    assert champion_challenger([0.9], [0.8], [1])["automatic_promotion"] is False
    assert drift_report([0.1, 0.2], [0.8, 0.9], 0.9, 0.6)["status"] == "REVIEW"
    assert drift_report([], [], 0.8, 0.5)["status"] == "INSUFFICIENT_DATA"


def test_benchmark_protocol_dual_review_splits_and_classical_baselines():
    row = {
        "observation_id": "a-2024",
        "company_id": "a",
        "fiscal_year": 2024,
        "as_of_date": "2025-01-01",
        "label_available_at": "2026-01-01",
        "split": "train",
        "source_url": "https://sec.gov/a",
        "source_hash": "abc",
        "review_status": "adjudicated",
    }
    assert validate_company_year_manifest([row])["valid"]
    leaking = [row, {**row, "observation_id": "a-2025", "split": "test"}]
    assert not validate_company_year_manifest(leaking)["company_disjoint"]
    assert adjudicate_label(1, 0, None)["status"] == "ADJUDICATION_REQUIRED"
    assert adjudicate_label(1, 1, None)["label"] == 1
    model = fit_logistic_baseline([[0], [1], [2], [3]], [0, 0, 1, 1])
    probabilities = predict_logistic(model, [[0], [3]])
    assert probabilities[0] < probabilities[1]
    assert fit_decision_stump([[0], [1], [2]], [0, 0, 1])["feature"] == 0
    assert selective_metrics([0, 1], [0.2, None])["coverage"] == 0.5
    assert calibration_curve([0, 1], [0.1, 0.9], 2)[0]["count"] == 1
    agreement = inter_rater_agreement([0, 1, 1, None], [0, 1, 0, 1])
    assert agreement["n"] == 3 and agreement["cohen_kappa"] == 0.4
    assert inter_rater_agreement([None], [None])["cohen_kappa"] is None


def test_structured_observability_redacts_sensitive_fields(caplog):
    logger = logging.getLogger("finrisk-test")
    with caplog.at_level(logging.INFO):
        identifier = bind_correlation_id("trace-1")
        structured_event(
            logger, "assessment.started", organization_id="org", api_key="secret"
        )
        with traced_stage(logger, "fusion"):
            pass
    assert identifier == "trace-1"
    assert "secret" not in caplog.text and "trace-1" in caplog.text


def test_agent_emits_versioned_proof_and_snapshot():
    evidence = Evidence(
        "10-K",
        9,
        "Current assets 80; current liabilities 100",
        2025,
        verification_status="verified",
    )
    state = FinancialRiskAgent(ROOT).run(
        "Trace Co",
        2025,
        {"current_assets": 80, "current_liabilities": 100, "cash": 5},
        source_map={"current_assets": [evidence], "current_liabilities": [evidence]},
    )
    assert state.decision_trace["verified_path_count"] >= 1
    assert state.analysis_snapshot["input_hash"]
    assert state.analysis_snapshot["component_versions"]["decision_policy"]
    replayed = FinancialRiskAgent(ROOT).replay(
        AnalysisSnapshot(**state.analysis_snapshot)
    )
    assert replayed["status"] == "REPLAYED"
    assert replayed["diff"]["match"] is True


def test_snapshot_requires_entity_in_callers_tenant():
    service = EnterpriseRiskService()
    first = service.create_organization("First", "admin-a")
    second = service.create_organization("Second", "admin-b")
    first_actor = Principal("analyst-a", first.id, Role.ANALYST)
    second_actor = Principal("analyst-b", second.id, Role.ANALYST)
    entity = service.create_entity(first_actor, "First Entity")
    foreign_snapshot = create_snapshot(
        second.id,
        entity.id,
        {"cash": 1},
        {"decision": "REVIEW"},
        {"10-K": "hash"},
        {"rules": "v1"},
    )
    with pytest.raises(KeyError):
        service.save_snapshot(second_actor, foreign_snapshot)
