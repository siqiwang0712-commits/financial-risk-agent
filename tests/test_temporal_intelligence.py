import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from finrisk.agent import FinancialRiskAgent
from finrisk.agent.review import StructuredJudgement, three_role_review
from finrisk.api import app
from finrisk.enterprise.applicability import (
    ApplicabilityStatus,
    applicability_report,
    route_model,
)
from finrisk.enterprise.calibration import (
    brier_score,
    expected_calibration_error,
    reliability_diagram,
    risk_coverage_curve,
    selective_decision,
)
from finrisk.enterprise.decision_bundle import (
    build_decision_bundle,
    verify_decision_bundle,
)
from finrisk.enterprise.domain import (
    Principal,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
    Role,
    new_id,
)
from finrisk.enterprise.evidence_graph import (
    EvidenceNode,
    EvidenceRelation,
    TemporalEvidenceGraph,
)
from finrisk.enterprise.governance import compare_system_versions
from finrisk.enterprise.service import EnterpriseRiskService
from finrisk.enterprise.temporal import (
    EntityRiskState,
    RiskSnapshot,
    compare_risk_snapshots,
)
from finrisk.human_study import summarize_study, validate_study_rows
from finrisk.xbrl import SecClient

ROOT = Path(__file__).resolve().parents[1]


def snapshot(period, score, liquidity, cash, evidence):
    return RiskSnapshot("entity-1", period, f"filing-{period}", score, {"liquidity": liquidity}, {"cash": cash}, {"liquidity": evidence}, "FLAG", 0.8, 0.7)


def test_temporal_state_delta_and_attribution():
    previous = snapshot("2023", 40, 35, 100, ["path-old"])
    current = snapshot("2024", 55, 43, 70, ["path-new"])
    delta = compare_risk_snapshots(previous, current)
    assert delta.score_change == 15
    assert delta.dimension_changes == {"liquidity": 8}
    assert delta.metric_changes == {"cash": -30}
    assert delta.attribution[0]["evidence_path_ids"] == ("path-new",)
    assert delta.evidence_delta.added == ("path-new",)
    state = EntityRiskState("entity-1")
    assert state.update(previous) is None
    assert state.update(current) == delta and state.current == current
    with pytest.raises(ValueError):
        state.update(current)
    with pytest.raises(ValueError, match="reporting-period order"):
        state.update(snapshot("2022", 20, 20, 120, []))
    with pytest.raises(ValueError):
        compare_risk_snapshots(previous, snapshot("2025", 1, 1, 1, []).__class__("other", "2025", "f", 1, {}, {}, {}, "PASS", 1))


def test_temporal_evidence_graph_relations_and_paths():
    graph = TemporalEvidenceGraph()
    for node in (
        EvidenceNode("doc", "document", "2024", {}),
        EvidenceNode("fact", "fact", "2024", {"value": 70}),
        EvidenceNode("decision", "decision", "2024", {"state": "REVIEW"}),
    ):
        graph.add_node(node)
    graph.link("doc", "fact", EvidenceRelation.DERIVED_FROM, "XBRL fact")
    graph.link("fact", "decision", EvidenceRelation.SUPPORTS, "liquidity driver")
    assert graph.paths_to("decision") == [["doc", "fact", "decision"]]
    assert graph.to_dict()["edges"][1]["relation"] == EvidenceRelation.SUPPORTS
    with pytest.raises(KeyError):
        graph.link("missing", "decision", EvidenceRelation.INVALIDATES, "bad")


def test_applicability_router():
    facts = {name: 1 for name in ("working_capital", "total_assets", "retained_earnings", "ebit", "market_value_equity", "total_liabilities", "revenue")}
    assert route_model("altman", "manufacturing", facts).status is ApplicabilityStatus.APPLICABLE
    bank = route_model("altman", "bank", facts)
    assert bank.status is ApplicabilityStatus.NOT_APPLICABLE
    assert route_model("altman", "software", facts).status is ApplicabilityStatus.LIMITED
    assert len(applicability_report("bank", {})) == 4
    with pytest.raises(KeyError):
        route_model("unknown", "industrial", {})
    bank_state = FinancialRiskAgent(ROOT).run(
        "Bank-like Co",
        2025,
        {
            "total_assets": 100,
            "total_liabilities": 90,
            "current_assets": 20,
            "current_liabilities": 10,
            "net_income": 2,
        },
        entity_type="bank",
    )
    assert all(model["output"] is None for model in bank_state.assessment["models"])
    assert all(
        model["applicability"].startswith("NOT_APPLICABLE")
        for model in bank_state.assessment["models"]
    )


def test_calibration_and_selective_automation():
    labels, probabilities = [0, 1], [0.2, 0.8]
    assert brier_score(labels, probabilities) == 0.04
    assert expected_calibration_error(labels, probabilities, 2) == 0.2
    assert len(reliability_diagram(labels, probabilities, 2)) == 2
    curve = risk_coverage_curve(labels, probabilities, [0.5, 0.9])
    assert curve[-1]["coverage"] == 0.5
    assert selective_decision("PASS", 0.2, 0.9, 0.1, {})["decision"] == "ABSTAIN"
    assert selective_decision("PASS", 0.9, 0.5, 0.1, {})["decision"] == "REVIEW"
    assert selective_decision("PASS", 0.9, 0.9, 0.1, {})["automation_allowed"]
    with pytest.raises(ValueError):
        brier_score([], [])


def test_three_role_review_rejects_unsupported_and_population_mismatch():
    paths = {"P1": {"evidence_path_status": "VERIFIED"}}
    accepted = three_role_review([StructuredJudgement("Liquidity risk", "liquidity", "material", ("P1",))], paths)
    assert accepted["verifier"]["status"] == "VERIFIED"
    rejected = three_role_review([StructuredJudgement("Fraud proven", "accounting", "material", ("missing",), "altman")], paths, {"altman": "NOT_APPLICABLE"})
    assert rejected["recommended_decision"] == "REVIEW"
    assert {item["code"] for item in rejected["critic"]} == {"UNSUPPORTED_CLAIM", "MODEL_POPULATION_MISMATCH", "OVERSTATED_CONCLUSION"}


def test_immutable_decision_bundle_and_agent_integration():
    bundle = build_decision_bundle("org", "entity", {"10-K": "abc"}, {"cash": 1}, {"decision": "REVIEW"}, {"score": 50}, [], {"metrics": {}}, [], {"rules": "v1", "calibration": "none"}, "REVIEW")
    assert verify_decision_bundle(bundle)
    altered = bundle.__class__(**{**bundle.to_dict(), "final_decision": "PASS"})
    assert not verify_decision_bundle(altered)
    state = FinancialRiskAgent(ROOT).run("Temporal Co", 2025, {"current_assets": 80, "current_liabilities": 100, "cash": 5})
    assert state.decision_bundle["bundle_hash"]
    assert state.role_review["verifier"]["status"] in {"VERIFIED", "REJECTED"}


def test_full_case_mitigation_resolution_and_reopen_loop():
    service = EnterpriseRiskService()
    org = service.create_organization("Org", "admin")
    analyst = Principal("analyst", org.id, Role.ANALYST)
    reviewer = Principal("reviewer", org.id, Role.REVIEWER)
    entity = service.create_entity(analyst, "Issuer")
    case = RiskCase(new_id("case"), org.id, entity.id, RiskDomain.LIQUIDITY, "high", "deteriorating", 0.8, 0.9, decision_trace={"verified_path_count": 1})
    service.create_case(analyst, case)
    service.add_action(analyst, case.id, "Extend maturity", "treasurer", "2027-01-01")
    service.transition(reviewer, case.id, RiskCaseStatus.OPEN)
    service.transition(reviewer, case.id, RiskCaseStatus.UNDER_REVIEW)
    with pytest.raises(ValueError, match="resolution evidence"):
        service.transition(reviewer, case.id, RiskCaseStatus.RESOLVED)
    service.add_resolution_evidence(reviewer, case.id, "evidence-1")
    resolved = service.transition(reviewer, case.id, RiskCaseStatus.RESOLVED)
    assert resolved.resolution_evidence == ["evidence-1"]
    reopened = service.reopen(reviewer, case.id, "new filing breached limit")
    assert reopened.status is RiskCaseStatus.OPEN and reopened.monitoring_state == "reopened"


def test_champion_challenger_system_gate():
    base = {"f1": 0.6, "balanced_accuracy": 0.6, "false_negative_rate": 0.2, "calibration_error": 0.1, "coverage": 0.8, "abstention_rate": 0.2, "evidence_verification_error": 0.01, "latency_ms": 100, "cost_usd": 0.1}
    better = {**base, "f1": 0.7, "balanced_accuracy": 0.7, "latency_ms": 120}
    assert compare_system_versions(base, better)["recommendation"] == "PROMOTE"
    unsafe = {**better, "false_negative_rate": 0.3}
    assert compare_system_versions(base, unsafe)["recommendation"] == "DO_NOT_PROMOTE"
    with pytest.raises(ValueError):
        compare_system_versions({}, {})


def test_sec_ticker_to_latest_filing_main_path():
    client = SecClient("FinRisk test@example.com")
    responses = {
        "https://www.sec.gov/files/company_tickers.json": {"0": {"ticker": "ACME", "cik_str": 42}},
        "https://data.sec.gov/submissions/CIK0000000042.json": {"filings": {"recent": {"form": ["8-K", "10-Q"], "accessionNumber": ["x", "0001-24-000002"], "primaryDocument": ["x.htm", "q.htm"], "filingDate": ["2024-01-01", "2024-05-01"], "reportDate": ["2023-12-31", "2024-03-31"]}}},
    }
    client.get_json = lambda url, cache_key=None: responses[url]
    filing = client.latest_filing("acme")
    assert filing["cik"] == "0000000042" and filing["form"] == "10-Q"
    assert filing["filing_url"].endswith("/q.htm")


def test_human_study_pipeline_is_explicitly_synthetic():
    rows = [
        {"participant_id": "p1", "condition": "human_only", "case_id": "c1", "analysis_seconds": 100, "missed_risks": 1, "unsupported_claims": 1, "citation_errors": 0, "overrides": 0, "decision": "FLAG", "gold_decision": "FLAG"},
        {"participant_id": "p1", "condition": "finrisk_assisted", "case_id": "c2", "analysis_seconds": 80, "missed_risks": 0, "unsupported_claims": 0, "citation_errors": 0, "overrides": 1, "decision": "REVIEW", "gold_decision": "FLAG"},
    ]
    assert validate_study_rows(rows)["valid"]
    result = summarize_study(rows, synthetic=True)
    assert result["status"] == "SYNTHETIC_DEMO" and result["participant_count"] == 1
    incidents = json.loads((ROOT / "failure_lab" / "incidents.json").read_text())
    assert all({"failure", "impact", "expected_response", "regression_test"} <= item.keys() for item in incidents)
    test_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "tests").glob("test_*.py")
    )
    assert all(
        f"def {incident['regression_test']}(" in test_source for incident in incidents
    )


def test_temporal_applicability_and_selective_api_flow():
    client = TestClient(app)
    org = client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "Timeline Org", "actor_id": "admin"},
    ).json()
    headers = {"X-API-Key": org["api_key"]}
    entity = client.post(
        "/api/v1/enterprise/entities", headers=headers, json={"name": "Issuer"}
    ).json()
    for period, score in (("2023", 30), ("2024", 45)):
        response = client.post(
            f"/api/v1/enterprise/entities/{entity['id']}/risk-snapshots",
            headers=headers,
            json={
                "period": period,
                "filing_id": f"filing-{period}",
                "risk_score": score,
                "dimension_scores": {"liquidity": score},
                "metrics": {"cash": 100 - score},
                "evidence_paths": {"liquidity": [f"path-{period}"]},
                "decision": "REVIEW",
                "coverage": 0.8,
                "reliability": 0.7,
            },
        )
        assert response.status_code == 200
    timeline = client.get(
        f"/api/v1/enterprise/entities/{entity['id']}/risk-timeline", headers=headers
    ).json()
    assert timeline[1]["delta"]["score_change"] == 15
    applicability = client.post(
        "/api/v1/enterprise/applicability",
        headers=headers,
        json={"industry": "bank", "facts": {}},
    ).json()
    assert all(item["status"] == "NOT_APPLICABLE" for item in applicability)
    decision = client.post(
        "/api/v1/enterprise/selective-decision",
        headers=headers,
        json={
            "proposed_decision": "PASS",
            "coverage": 0.2,
            "reliability": None,
            "disagreement": 0.1,
        },
    ).json()
    assert decision["decision"] == "ABSTAIN"
