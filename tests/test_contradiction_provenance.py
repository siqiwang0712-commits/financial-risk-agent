from copy import deepcopy
from pathlib import Path

import pytest
from finrisk.domain import Evidence
from finrisk.enterprise.decision import (
    build_decision_trace,
    create_snapshot,
    verified_material_path,
    verified_numeric_inputs,
)
from finrisk.enterprise.domain import (
    Principal,
    RiskCase,
    RiskCaseStatus,
    RiskDomain,
    Role,
    new_id,
)
from finrisk.enterprise.service import EnterpriseRiskService, verified_evidence_ids
from finrisk.pipeline import FinRiskPipeline

ROOT = Path(__file__).resolve().parents[1]
CURRENT = {"current_assets": 50, "current_liabilities": 100, "cash": 1,
           "operating_cash_flow": 1, "short_term_debt": 200}
PREVIOUS = {"cash": 100, "operating_cash_flow": 100, "short_term_debt": 100}


def contradiction_paths(source_map=None):
    assessment = FinRiskPipeline(ROOT).assess(
        "Synthetic contradiction", 2025, CURRENT, PREVIOUS,
        {1: "Liquidity remains strong."}, source_map=source_map,
    )
    trace = build_decision_trace(assessment.to_dict(), {"proposed_decision": "FLAG"})
    paths = [p for p in trace["paths"] if p["rule_or_model"] == "narrative_numeric_consistency"]
    assert paths
    return paths


def references():
    result = {}
    for period, values in ((2025, CURRENT), (2024, PREVIOUS)):
        for name, value in values.items():
            result.setdefault(name, []).append(Evidence(
                "Synthetic filing", 1, f"{name}={value}", period,
                value=value, verified=True, verification_status="verified",
            ))
    return result


def test_verified_quote_does_not_verify_unproven_numeric_contradiction():
    for path in contradiction_paths():
        assert path["source_evidence"][0]["verification_status"] == "verified"
        assert path["required_inputs"]
        assert path["evidence_path_status"] == "UNVERIFIED"
        assert not verified_material_path(path)


def test_contradiction_requires_current_and_prior_numeric_provenance():
    complete = references()
    assert all(verified_material_path(p) for p in contradiction_paths(complete))
    incomplete = deepcopy(complete)
    incomplete["cash"] = [ev for ev in incomplete["cash"] if ev.fiscal_year == 2025]
    assert all(not verified_material_path(p) for p in contradiction_paths(incomplete))


@pytest.mark.parametrize("required,provenance", [([], {}), (["cash"], {"cash": "verified"}),
    (["cash"], {"cash": [None]}), ([{}], {}), ("cash", {}),
    (["cash"], {"cash": [{"verification_status": "located"}]}), (["cash"], None)])
def test_malformed_numeric_provenance_fails_closed(required, provenance):
    assert not verified_numeric_inputs(required, provenance)


@pytest.mark.parametrize("target", [RiskCaseStatus.ACCEPTED, RiskCaseStatus.RESOLVED])
def test_legacy_quote_only_path_cannot_authorize_workflow_or_resolution_evidence(target):
    service = EnterpriseRiskService()
    org = service.create_organization("Synthetic tenant", "reviewer")
    principal = Principal("reviewer", org.id, Role.ADMIN)
    entity = service.create_entity(principal, "Synthetic entity")
    legacy = {"rule_or_model": "narrative_numeric_consistency", "risk_domain": "liquidity",
              "evidence_path_status": "VERIFIED", "source_evidence": [{"verification_status": "verified"}]}
    snapshot = create_snapshot(org.id, entity.id, {},
                               {"agent": {"decision_trace": {"paths": [legacy]}}}, {}, {})
    service.save_snapshot(principal, snapshot)
    case = RiskCase(new_id("case"), org.id, entity.id, RiskDomain.LIQUIDITY,
                    "high", "stable", .5, .5, snapshot_id=snapshot.id)
    service.create_case(principal, case)
    assert verified_evidence_ids(snapshot, "liquidity") == set()
    with pytest.raises(ValueError, match="verified server-side evidence path"):
        service.transition(principal, case.id, target)
