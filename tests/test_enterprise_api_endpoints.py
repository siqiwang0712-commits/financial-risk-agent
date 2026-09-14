"""End-to-end exercise of the enterprise endpoints.

`docs/audit_report_2026-09-13.md` found several defects that were only reachable
through the HTTP layer - a malformed policy stored and then raising `TypeError`
(HTTP 500) on evaluation, a bare `metrics` body that bypassed the numeric guard
every other endpoint applies, and a fusion dispatcher that special-cased one
method name by string. Those are exercised here against a real `TestClient`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from finrisk.api import app
from finrisk.enterprise.fusion import FUSION_METHODS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tenant() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(app)
    response = client.post(
        "/api/v1/enterprise/organizations",
        json={"name": "endpoint tenant", "actor_id": "endpoint-admin"},
    )
    assert response.status_code == 200
    return client, {"X-API-Key": response.json()["api_key"]}


def _entity(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/enterprise/entities",
        headers=headers,
        json={"name": "Subsidiary", "sector": "industrial"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _snapshot(
    client: TestClient,
    headers: dict[str, str],
    entity_id: str,
    domain: str = "cash_flow",
) -> str:
    """An analysis snapshot carrying one verified, sourced evidence path.

    The path is what `transition` to ACCEPTED/RESOLVED requires, so a case in the
    matching domain can be accepted and a case in any other domain cannot.
    """
    response = client.post(
        "/api/v1/enterprise/snapshots",
        headers=headers,
        json={
            "entity_id": entity_id,
            "frozen_input": {"cash": 100.0},
            "frozen_output": {
                "risk_level": "high",
                "agent": {
                    "risk_severity": "high",
                    "risk_trajectory": "stable",
                    "evidence_coverage": 0.7,
                    "epistemics": {"evidence_quality": 0.8},
                    "decision_trace": {
                        "paths": [
                            {
                                "reason_code": "CFL_002",
                                "risk_domain": domain,
                                "evidence_path_status": "VERIFIED",
                                "source_evidence": [
                                    {
                                        "source": "10-K",
                                        "quote": "operating cash flow fell",
                                        "verification_status": "verified",
                                    }
                                ],
                            }
                        ]
                    },
                },
            },
            "document_versions": {"10-K": "hash"},
            "component_versions": {"rules": "v1"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


# --------------------------------------------------------------------------- #
# Every endpoint is authenticated
# --------------------------------------------------------------------------- #
def test_enterprise_endpoints_require_a_principal(tenant):
    client, headers = tenant
    assert client.get("/api/v1/enterprise/overview").status_code == 401
    assert client.get("/api/v1/enterprise/audit-events").status_code == 401
    assert client.post("/api/v1/enterprise/fusion", json={}).status_code == 401
    assert client.get(
        "/api/v1/enterprise/overview", headers={"X-API-Key": "frk_invalid"}
    ).status_code == 401
    assert client.get("/api/v1/enterprise/overview", headers=headers).status_code == 200


# --------------------------------------------------------------------------- #
# H2 - the policy evaluation path
# --------------------------------------------------------------------------- #
def test_a_valid_policy_is_stored_and_evaluated(tenant):
    client, headers = tenant
    created = client.post(
        "/api/v1/enterprise/policies",
        headers=headers,
        json={
            "name": "Limits",
            "version": 1,
            "thresholds": {"debt": {"warning": 0.4, "critical": 0.6}},
        },
    )
    assert created.status_code == 200
    policy_id = created.json()["id"]
    evaluated = client.post(
        f"/api/v1/enterprise/policies/{policy_id}/evaluate",
        headers=headers,
        json={"debt": 0.95},
    )
    assert evaluated.status_code == 200
    assert evaluated.json()[0]["status"] == "critical"


def test_a_malformed_policy_is_refused_at_the_boundary(tenant):
    client, headers = tenant
    for thresholds in (
        {"debt": {"warning": "low", "critical": "high"}},
        {"debt": "abc"},
        {"debt": {"risk_direction": "higher_is_worse"}},
    ):
        response = client.post(
            "/api/v1/enterprise/policies",
            headers=headers,
            json={"name": "bad", "version": 1, "thresholds": thresholds},
        )
        # A 422 here is what keeps the malformed policy out of the store; the
        # audited behaviour stored it and returned a 500 on the next evaluation.
        assert response.status_code == 422, thresholds


def test_policy_evaluation_refuses_non_finite_metrics(tenant):
    client, headers = tenant
    created = client.post(
        "/api/v1/enterprise/policies",
        headers=headers,
        json={
            "name": "Limits",
            "version": 1,
            "thresholds": {"debt": {"warning": 0.4, "critical": 0.6}},
        },
    )
    policy_id = created.json()["id"]
    for metrics in ({"debt": "high"}, {"debt": True}):
        response = client.post(
            f"/api/v1/enterprise/policies/{policy_id}/evaluate",
            headers=headers,
            json=metrics,
        )
        assert response.status_code == 422, metrics
    assert (
        client.post(
            "/api/v1/enterprise/policies/missing/evaluate",
            headers=headers,
            json={"debt": 0.5},
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# H10 - the fusion dispatcher
# --------------------------------------------------------------------------- #
def test_every_registered_fusion_method_dispatches(tenant):
    client, headers = tenant
    for method in FUSION_METHODS:
        response = client.post(
            "/api/v1/enterprise/fusion",
            headers=headers,
            json={
                "method": method,
                "scores": {"liquidity": 60.0, "cash_flow": 30.0},
                "weights": {"liquidity": 1.0, "cash_flow": 1.0},
                "coverage": 0.8,
                "confidence": 0.7,
                "decision_policy": {"critical_threshold": 0.8, "review_threshold": 0.5},
            },
        )
        assert response.status_code == 200, (method, response.text)
        assert "decision" in response.json()
    assert (
        client.post(
            "/api/v1/enterprise/fusion",
            headers=headers,
            json={
                "method": "not_a_method",
                "scores": {},
                "coverage": 0.8,
                "confidence": 0.7,
            },
        ).status_code
        == 422
    )


# --------------------------------------------------------------------------- #
# Scenario, applicability and selective-decision endpoints
# --------------------------------------------------------------------------- #
def test_scenario_endpoint_rejects_unknown_shocks(tenant):
    client, headers = tenant
    ok = client.post(
        "/api/v1/enterprise/scenarios",
        headers=headers,
        json={
            "year": 2025,
            "baseline": {"revenue": 100.0, "gross_profit": 40.0},
            "shocks": {"revenue_pct": -0.1},
        },
    )
    assert ok.status_code == 200
    assert ok.json()["calculation_mode"] == "deterministic"
    bad = client.post(
        "/api/v1/enterprise/scenarios",
        headers=headers,
        json={"year": 2025, "baseline": {"revenue": 100.0}, "shocks": {"invented": 1.0}},
    )
    assert bad.status_code == 422


def test_applicability_and_selective_decision_endpoints(tenant):
    client, headers = tenant
    report = client.post(
        "/api/v1/enterprise/applicability",
        headers=headers,
        json={"industry": "manufacturing", "facts": {"total_assets": 100.0}},
    )
    assert report.status_code == 200
    assert {item["model"] for item in report.json()} == {
        "altman",
        "beneish",
        "piotroski",
        "ohlson",
    }
    uncalibrated = client.post(
        "/api/v1/enterprise/selective-decision",
        headers=headers,
        json={
            "proposed_decision": "PASS",
            "coverage": 0.9,
            "disagreement": 0.0,
            "policy": {},
        },
    )
    assert uncalibrated.status_code == 200
    assert uncalibrated.json()["decision"] == "ABSTAIN"
    assert uncalibrated.json()["automation_allowed"] is False


# --------------------------------------------------------------------------- #
# The case lifecycle, including the reopened state machine
# --------------------------------------------------------------------------- #
def test_case_lifecycle_and_the_reopen_guard(tenant):
    client, headers = tenant
    entity_id = _entity(client, headers)
    snapshot_id = _snapshot(client, headers, entity_id, domain="cash_flow")

    created = client.post(
        "/api/v1/enterprise/risk-cases",
        headers=headers,
        json={
            "entity_id": entity_id,
            "domain": "cash_flow",
            "snapshot_id": snapshot_id,
        },
    )
    assert created.status_code == 200, created.text
    case_id = created.json()["id"]

    assert len(client.get("/api/v1/enterprise/risk-cases", headers=headers).json()) == 1

    def transition(target: str):
        return client.post(
            f"/api/v1/enterprise/risk-cases/{case_id}/transition",
            headers=headers,
            json={"target": target},
        )

    # `detected -> under_review` is not a legal step; the table says so.
    assert transition("under_review").status_code == 422
    assert transition("open").status_code == 200
    assert transition("under_review").status_code == 200
    # Accepted now requires a verified, sourced evidence path in this domain, and
    # the snapshot provides one.
    assert transition("accepted").status_code == 200

    override = client.post(
        f"/api/v1/enterprise/risk-cases/{case_id}/override",
        headers=headers,
        json={"original": "FLAG", "override": "PASS", "reason": "reviewed"},
    )
    assert override.status_code == 200

    action = client.post(
        f"/api/v1/enterprise/risk-cases/{case_id}/actions",
        headers=headers,
        json={"description": "Hedge", "owner_id": "analyst", "due_date": "2026-01-01"},
    )
    assert action.status_code == 200

    evidence = client.post(
        f"/api/v1/enterprise/risk-cases/{case_id}/resolution-evidence",
        headers=headers,
        json={"evidence_id": "ev_1"},
    )
    assert evidence.status_code == 200

    # Reopening an accepted case is legal, and goes through the same table.
    reopened = client.post(
        f"/api/v1/enterprise/risk-cases/{case_id}/reopen",
        headers=headers,
        json={"reason": "new filing"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"

    # An open case cannot be reopened again.
    assert (
        client.post(
            f"/api/v1/enterprise/risk-cases/{case_id}/reopen",
            headers=headers,
            json={"reason": "again"},
        ).status_code
        == 422
    )

    overview = client.get("/api/v1/enterprise/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["case_count"] == 1
    assert overview.json()["open_case_count"] == 1
    assert overview.json()["by_domain"] == {"cash_flow": 1}

    events = client.get("/api/v1/enterprise/audit-events", headers=headers)
    assert events.status_code == 200
    assert events.json()


def test_a_case_cannot_be_accepted_without_a_matching_evidence_path(tenant):
    """The gate that made `RiskDomain.COVENANT`/`COUNTERPARTY` unreachable."""
    client, headers = tenant
    entity_id = _entity(client, headers)
    snapshot_id = _snapshot(client, headers, entity_id, domain="cash_flow")
    created = client.post(
        "/api/v1/enterprise/risk-cases",
        headers=headers,
        json={
            "entity_id": entity_id,
            "domain": "liquidity",
            "snapshot_id": snapshot_id,
        },
    )
    assert created.status_code == 200
    case_id = created.json()["id"]
    for target in ("open", "under_review"):
        client.post(
            f"/api/v1/enterprise/risk-cases/{case_id}/transition",
            headers=headers,
            json={"target": target},
        )
    response = client.post(
        f"/api/v1/enterprise/risk-cases/{case_id}/transition",
        headers=headers,
        json={"target": "accepted"},
    )
    assert response.status_code == 422


def test_case_creation_rejects_an_unknown_snapshot(tenant):
    client, headers = tenant
    entity_id = _entity(client, headers)
    response = client.post(
        "/api/v1/enterprise/risk-cases",
        headers=headers,
        json={"entity_id": entity_id, "domain": "liquidity", "snapshot_id": "missing"},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Risk snapshots and the timeline
# --------------------------------------------------------------------------- #
def test_risk_timeline_requires_ordered_periods(tenant):
    client, headers = tenant
    entity_id = _entity(client, headers)
    first = client.post(
        f"/api/v1/enterprise/entities/{entity_id}/risk-snapshots",
        headers=headers,
        json={
            "period": "2024",
            "filing_id": "f1",
            "risk_score": 40.0,
            "dimension_scores": {"liquidity": 40.0},
            "metrics": {"current_ratio": 1.2},
            "evidence_paths": {},
            "decision": "PASS",
            "coverage": 0.8,
        },
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/v1/enterprise/entities/{entity_id}/risk-snapshots",
        headers=headers,
        json={
            "period": "2025",
            "filing_id": "f2",
            "risk_score": 70.0,
            "dimension_scores": {"liquidity": 70.0},
            "metrics": {"current_ratio": 0.9},
            "evidence_paths": {},
            "decision": "FLAG",
            "coverage": 0.8,
        },
    )
    assert second.status_code == 200
    timeline = client.get(
        f"/api/v1/enterprise/entities/{entity_id}/risk-timeline", headers=headers
    )
    assert timeline.status_code == 200
    rows = timeline.json()
    assert [row["period"] for row in rows] == ["2024", "2025"]
    # The first period has nothing to compare against; the second carries a delta.
    assert rows[0]["delta"] is None
    assert rows[1]["delta"] is not None
    assert (
        client.get(
            "/api/v1/enterprise/entities/missing/risk-timeline", headers=headers
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# Replay diff
# --------------------------------------------------------------------------- #
def test_snapshot_replay_diff_reports_a_divergence(tenant):
    client, headers = tenant
    entity_id = _entity(client, headers)
    snapshot_id = _snapshot(client, headers, entity_id)
    # `replay_diff` hashes the replayed output, so an arbitrary dict is a
    # divergence rather than an error.
    divergent = client.post(
        f"/api/v1/enterprise/snapshots/{snapshot_id}/replay-diff",
        headers=headers,
        json={"replayed_output": {"risk_level": "low"}},
    )
    assert divergent.status_code == 200
    assert divergent.json()["match"] is False
    assert divergent.json()["classification"] == "DRIFT_DETECTED"
    assert divergent.json()["historical_output_hash"]
    assert (
        client.post(
            "/api/v1/enterprise/snapshots/missing/replay-diff",
            headers=headers,
            json={"replayed_output": {}},
        ).status_code
        == 404
    )
