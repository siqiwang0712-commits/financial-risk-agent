import json
from pathlib import Path

from finrisk.agent.orchestrator import FinancialRiskAgent
from finrisk.contradictions import detect_contradictions, evaluate_claim_consistency
from finrisk.domain import Evidence, NarrativeClaim
from finrisk.enterprise.fusion import (
    RiskContribution,
    fuse_verified_contributions,
    hierarchical_escalation,
)
from finrisk.enterprise.integrity import CalibrationStatus, epistemic_summary


def test_severe_and_missing_dimensions_cannot_dilute_supported_risk():
    severe = hierarchical_escalation({"liquidity": 85}, 0.8, 0.8)
    with_ordinary = hierarchical_escalation(
        {"liquidity": 85, "profitability": 20, "cash_flow": None}, 0.8, 0.8
    )
    assert with_ordinary.score >= severe.score == 85
    assert "CRITICAL_DIMENSION_ESCALATION" in with_ordinary.reason_codes


def test_adverse_evidence_monotonicity_and_duplicate_suppression():
    base = fuse_verified_contributions(
        [RiskContribution("liquidity", 45, "ev-1")], 0.8, 0.8
    )
    augmented = fuse_verified_contributions(
        [
            RiskContribution("liquidity", 45, "ev-1"),
            RiskContribution("liquidity", 45, "ev-1"),
            RiskContribution("cash_flow", 70, "ev-2"),
        ],
        0.8,
        0.8,
    )
    assert augmented.score >= base.score
    assert augmented.drivers.count("cash_flow") <= 1
    assert "DUPLICATE_EVIDENCE_SUPPRESSED" in augmented.reason_codes
    assert "SEVERE_VERIFIED_SIGNAL" in augmented.reason_codes


def test_claim_context_incomplete_is_not_a_contradiction():
    claim = NarrativeClaim(
        "Liquidity remains strong",
        "liquidity",
        Evidence(
            "10-K",
            4,
            "Liquidity remains strong",
            2025,
            verification_status="verified",
        ),
        "positive",
        "overall_liquidity",
        "positive",
        "next_12_months",
        "management_statement",
        (),
        ("liquidity_position", "cash_generation", "funding_pressure"),
    )
    result = evaluate_claim_consistency(
        claim, {"current_ratio": 0.8, "cash_growth": -0.3}
    )
    assert result.classification == "INCOMPLETE_CONTEXT"
    assert result.reason_code == "CLAIM_CONTEXT_INCOMPLETE"
    assert result.missing_evidence_types == ("funding_pressure",)
    assert detect_contradictions([claim], {"current_ratio": 0.8, "cash_growth": -0.3}) == []


def test_disagreement_cannot_be_expressed_as_overconfident_probability():
    result = hierarchical_escalation(
        {"liquidity": 90, "profitability": 10}, 0.9, 0.95
    )
    epistemics = epistemic_summary(
        evidence_coverage=0.9,
        evidence_quality=0.95,
        disagreement=result.disagreement,
        reliability=0.99,
        calibration_status=CalibrationStatus.UNCALIBRATED,
    )
    assert result.decision == "REVIEW"
    assert "HIGH_MODEL_DISAGREEMENT" in result.reason_codes
    assert epistemics["reliability"] is None
    assert epistemics["probability"] is None


def test_component_telemetry_is_frozen_into_decision_bundle():
    root = Path(__file__).resolve().parents[1]
    current = {
        "cash": 10,
        "current_assets": 80,
        "total_assets": 150,
        "current_liabilities": 100,
        "total_liabilities": 110,
        "shareholder_equity": 40,
        "revenue": 100,
        "operating_income": 5,
        "net_income": 2,
        "operating_cash_flow": 1,
    }
    state = FinancialRiskAgent(root=root).run("Invariant Fixture", 2025, current)
    names = {item["component"] for item in state.component_telemetry}
    assert names == {
        "XBRL",
        "rules",
        "traditional_models",
        "LLM_narrative",
        "Critic",
        "Verifier",
        "fusion",
    }
    assert state.epistemics["calibration_status"] == "UNCALIBRATED"
    assert list(state.decision_bundle["component_telemetry"]) == state.component_telemetry
    assert state.decision_bundle["epistemics"]["probability"] is None


def test_v031_replay_is_separate_and_monotonic():
    root = Path(__file__).resolve().parents[1]
    run_manifest = json.loads(
        (root / "research/results/v0.3.1/run_manifest.json").read_text()
    )
    replay = json.loads(
        (root / "research/results/v0.3.1/decision_integrity_replay.json").read_text()
    )
    assert run_manifest["source_results_preserved"] == "research/results/public_v1"
    assert not run_manifest["predictive_superiority_claimed"]
    assert len(replay) == 3
    assert all(item["delta"] >= 0 for item in replay)


def test_fusion_is_monotonic_when_a_correlated_source_adds_a_dimension():
    """Adding adverse evidence must never lower the fused score.

    A global evidence cap used to drop the weaker dimension of a shared source,
    which reduced the escalation count and lowered the aggregate. The cap is now
    scoped per dimension, so this stays monotonic.
    """
    base = fuse_verified_contributions(
        [
            RiskContribution("liquidity", 55, "ev-1", evidence_group="g1"),
            RiskContribution("solvency", 60, "ev-2", evidence_group="g2"),
        ],
        0.9,
        0.9,
    )
    augmented = fuse_verified_contributions(
        [
            RiskContribution("liquidity", 55, "ev-1", evidence_group="g1"),
            RiskContribution("solvency", 60, "ev-2", evidence_group="g2"),
            RiskContribution("solvency", 60, "ev-3", evidence_group="g1"),
        ],
        0.9,
        0.9,
    )
    assert augmented.score >= base.score
