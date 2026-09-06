from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from finrisk.api import app
from finrisk.domain import Evidence, NarrativeClaim
from finrisk.enterprise.alerts import detect_alerts
from finrisk.enterprise.auth import authorize
from finrisk.enterprise.domain import (
    AuditEvent,
    PolicyVersion,
    Principal,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
    Role,
    new_id,
)
from finrisk.enterprise.fusion import (
    hierarchical_escalation,
    interaction_aware,
    max_severity,
    weighted_average,
)
from finrisk.enterprise.governance import experiment_run
from finrisk.enterprise.jobs import Job, JobQueue
from finrisk.enterprise.policy import evaluate_kri
from finrisk.enterprise.portfolio import portfolio_overview
from finrisk.enterprise.scenario import Scenario, apply_scenario, compare_scenario
from finrisk.enterprise.security import (
    SlidingWindowRateLimiter,
    issue_api_key,
    verify_api_key,
)
from finrisk.enterprise.service import EnterpriseRiskService
from finrisk.enterprise.storage import LocalDocumentStorage
from finrisk.enterprise.temporal import classify_trajectory
from finrisk.enterprise.tension import classify_tension


def test_security_storage_and_tenant_boundaries(tmp_path: Path):
    raw, credential = issue_api_key("org-a")
    assert verify_api_key(raw, credential)
    assert not verify_api_key(raw + "x", credential)
    limiter = SlidingWindowRateLimiter(2, 10)
    assert limiter.allow("org-a", 1) and limiter.allow("org-a", 2)
    assert not limiter.allow("org-a", 3)
    assert limiter.allow("org-a", 12)
    storage = LocalDocumentStorage(tmp_path)
    item = storage.put("org-a", "report.pdf", b"evidence")
    assert storage.get("org-a", "report.pdf") == b"evidence"
    assert len(item.sha256) == 64
    with pytest.raises(ValueError):
        storage.put("../other", "report.pdf", b"bad")
    with pytest.raises(PermissionError):
        authorize(Principal("u", "org-a", Role.ADMIN), "read", "org-b")


def test_fusion_is_failure_aware_and_not_probability():
    scores = {"liquidity": 85, "cash_flow": 25, "governance": None}
    assert (
        weighted_average(scores, {"liquidity": 1, "cash_flow": 1}, 0.8, 0.9).score == 55
    )
    assert max_severity(scores, 0.8, 0.9).score == 85
    assert hierarchical_escalation(scores, 0.8, 0.9).decision == "FLAG"
    assert (
        interaction_aware({"liquidity": 70, "solvency_leverage": 60}, 0.8, 0.9).score
        == 73
    )
    assert max_severity(scores, 0.2, 0.9).decision == "ABSTAIN"


def test_temporal_scenario_policy_alerts_and_tension():
    assert classify_trajectory([30]) == "insufficient_history"
    assert classify_trajectory([20, 45, 70]) == "sharply_deteriorating"
    assert classify_trajectory([75, 70]) == "persistent_weakness"
    assert classify_trajectory([80, 50]) == "recovery"
    assert classify_trajectory([30, 33, 31]) == "stable"
    base = {
        "revenue": 100,
        "gross_profit": 40,
        "operating_income": 20,
        "total_debt": 50,
        "interest_expense": 5,
        "operating_cash_flow": 12,
    }
    scenario = Scenario(
        "downside",
        revenue_pct=-0.1,
        margin_pp=-0.02,
        interest_rate_bp=100,
        cfo_pct=-0.2,
    )
    assert apply_scenario(base, scenario)["revenue"] == 90
    assert compare_scenario(base, 2025, scenario)["calculation_mode"] == "deterministic"
    policy = PolicyVersion(
        "p", "org", 1, "base", {"leverage": {"warning": 3.0, "critical": 5.0}}, "u"
    )
    assert evaluate_kri(policy, {"leverage": 4.0})[0]["status"] == "warning"
    assert {
        item["type"] for item in detect_alerts({"severity": 70, "limit_breached": True})
    } == {"LIMIT_BREACHED", "NEW_RISK"}
    evidence = Evidence(
        "10-K", 3, "Liquidity remains strong", 2025, verification_status="verified"
    )
    claim = NarrativeClaim(
        "Liquidity remains strong", "liquidity", evidence, "positive"
    )
    assert (
        classify_tension(claim, [], ["cash down", "ratio below 1"]).classification
        == "Material Contradiction"
    )


def test_jobs_portfolio_and_governance():
    queue = JobQueue()
    first = queue.enqueue(Job("org", "assessment", "same", {}))
    assert queue.enqueue(Job("org", "assessment", "same", {})).id == first.id
    assert queue.claim().attempts == 1
    queue.fail(first.id, "transient")
    assert queue.claim().attempts == 2
    queue.complete(first.id)
    assert queue.claim() is None
    case = RiskCase(
        new_id("case"),
        "org",
        "entity",
        RiskDomain.LIQUIDITY,
        "critical",
        "deteriorating",
        0.8,
        0.7,
    )
    assert portfolio_overview([case])["critical_open_count"] == 1
    with pytest.raises(ValueError):
        experiment_run(status="VALIDATED")


def test_service_workflow_policy_and_tension_branches():
    service = EnterpriseRiskService()
    org = service.create_organization("Tenant", "founder")
    admin = Principal("admin", org.id, Role.ADMIN)
    analyst = Principal("analyst", org.id, Role.ANALYST)
    reviewer = Principal("reviewer", org.id, Role.REVIEWER)
    entity = service.create_entity(analyst, "Subsidiary", "industrial")
    policy = service.create_policy(
        admin, "Limits", {"debt": {"warning": 1, "critical": 2}}, 1
    )
    assert evaluate_kri(policy, {"debt": None})[0]["status"] == "missing"
    case = RiskCase(
        new_id("case"),
        org.id,
        entity.id,
        RiskDomain.SOLVENCY,
        "high",
        "stable",
        0.7,
        0.8,
    )
    service.create_case(analyst, case)
    service.transition(reviewer, case.id, RiskCaseStatus.OPEN)
    with pytest.raises(ValueError):
        service.transition(reviewer, case.id, RiskCaseStatus.RESOLVED)
    service.override(reviewer, case.id, "FLAG", "PASS", "Committee accepted risk")
    with pytest.raises(PermissionError):
        service.create_policy(analyst, "Denied", {}, 2)
    assert service.repository.list_events(org.id)

    unverified = NarrativeClaim("Claim", "cash_flow", Evidence("doc", 1, "Claim"))
    assert (
        classify_tension(unverified, [], []).classification == "Insufficient Evidence"
    )
    verified = NarrativeClaim(
        "Claim",
        "cash_flow",
        Evidence("doc", 1, "Claim", verification_status="verified"),
    )
    assert classify_tension(verified, ["a"], []).classification == "Weakly Supported"
    assert classify_tension(verified, ["a", "b"], []).classification == "Supported"
    assert (
        classify_tension(verified, ["a"], ["b"]).classification == "Context-dependent"
    )
    assert classify_tension(verified, [], ["b"]).classification == "Tension"


def test_optional_postgres_adapter_with_fake_connection(tmp_path: Path):
    from finrisk.enterprise.postgres import PostgresEnterpriseRepository

    class Cursor:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, *args):
            self.calls.append(args)

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.commits = 0

        def cursor(self):
            return self.cursor_value

        def commit(self):
            self.commits += 1

    connection = Connection()
    repository = PostgresEnterpriseRepository(connection)
    migration = tmp_path / "migration.sql"
    migration.write_text("SELECT 1", encoding="utf-8")
    repository.migrate(migration)
    repository.append_audit_event(
        AuditEvent("e", "o", "u", "a", "case", "c", {"safe": True})
    )
    assert connection.commits == 2
    assert len(connection.cursor_value.calls) == 2


def test_enterprise_api_case_lifecycle_and_scenario():
    client = TestClient(app)
    org = client.post(
        "/api/v1/enterprise/organizations", json={"name": "Acme", "actor_id": "admin"}
    ).json()
    headers = {"X-API-Key": org["api_key"]}
    assert (
        client.get(
            "/api/v1/enterprise/risk-cases", headers={"X-API-Key": "frk_invalid"}
        ).status_code
        == 401
    )
    entity = client.post(
        "/api/v1/enterprise/entities", headers=headers, json={"name": "Acme Holdings"}
    ).json()
    created = client.post(
        "/api/v1/enterprise/risk-cases",
        headers=headers,
        json={
            "entity_id": entity["id"],
            "domain": "liquidity",
            "severity": "high",
            "confidence": 0.8,
            "evidence_coverage": 0.7,
            "rationale": "KRI breach",
        },
    )
    assert created.status_code == 200
    case_id = created.json()["id"]
    transitioned = client.post(
        f"/api/v1/enterprise/risk-cases/{case_id}/transition",
        headers=headers,
        json={"target": "open"},
    )
    assert transitioned.json()["status"] == "open"
    assert (
        client.get("/api/v1/enterprise/overview", headers=headers).json()[
            "open_case_count"
        ]
        == 1
    )
    assert client.get("/api/v1/enterprise/audit-events", headers=headers).json()
    policy = client.post(
        "/api/v1/enterprise/policies",
        headers=headers,
        json={
            "name": "Board appetite",
            "version": 1,
            "thresholds": {"debt": {"warning": 2, "critical": 4}},
        },
    )
    assert policy.status_code == 200
    evaluated = client.post(
        f"/api/v1/enterprise/policies/{policy.json()['id']}/evaluate",
        headers=headers,
        json={"debt": 3},
    )
    assert evaluated.json()[0]["status"] == "warning"
    other = client.post(
        "/api/v1/enterprise/organizations", json={"name": "Other", "actor_id": "other"}
    ).json()
    assert (
        client.post(
            f"/api/v1/enterprise/policies/{policy.json()['id']}/evaluate",
            headers={"X-API-Key": other["api_key"]},
            json={"debt": 3},
        ).status_code
        == 404
    )
    snapshot = client.post(
        "/api/v1/enterprise/snapshots",
        headers=headers,
        json={
            "entity_id": entity["id"],
            "frozen_input": {"cash": 1},
            "frozen_output": {"decision": "FLAG"},
            "document_versions": {"10-K": "hash"},
            "component_versions": {"rules": "r1"},
        },
    )
    assert snapshot.status_code == 200
    replay = client.post(
        f"/api/v1/enterprise/snapshots/{snapshot.json()['id']}/replay-diff",
        headers=headers,
        json={"replayed_output": {"decision": "FLAG"}},
    )
    assert replay.json()["match"] is True
    fusion = client.post(
        "/api/v1/enterprise/fusion",
        headers=headers,
        json={
            "method": "max_severity",
            "scores": {"liquidity": 80},
            "coverage": 0.9,
            "confidence": 0.8,
        },
    )
    assert fusion.json()["decision"] == "FLAG"
    scenario = client.post(
        "/api/v1/enterprise/scenarios",
        headers=headers,
        json={
            "year": 2025,
            "baseline": {"revenue": 100.0},
            "shocks": {"revenue_pct": -0.2},
        },
    )
    assert scenario.json()["stressed_values"]["revenue"] == 80


def test_enterprise_compute_endpoints_require_authentication():
    client = TestClient(app)
    fusion = client.post(
        "/api/v1/enterprise/fusion",
        json={
            "method": "max_severity",
            "scores": {"liquidity": 80},
            "coverage": 0.9,
            "confidence": 0.8,
        },
    )
    scenario = client.post(
        "/api/v1/enterprise/scenarios",
        json={
            "year": 2025,
            "baseline": {"revenue": 100.0},
            "shocks": {"revenue_pct": -0.2},
        },
    )
    assert fusion.status_code == 401
    assert scenario.status_code == 401
