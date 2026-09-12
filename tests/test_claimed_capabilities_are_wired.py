"""Regression guard for invariants the Agent must not silently break.

Each test here corresponds to a defect that previously existed and was invisible to
the suite: the published workflow trace disagreed with the decision it described,
narrative extraction ran twice per analysis, the same claim could be reported as
both a contradiction and a non-issue, and the outward-facing score was not the one
the decision was derived from. All of them are cross-component properties, which is
why no single-module test caught them.

These assert the *wiring*, not the algorithms.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from finrisk.agent import FinancialRiskAgent
from finrisk.enterprise.decision import canonical_hash
from finrisk.enterprise.fusion import interaction_aware
from finrisk.llm import MockNarrativeProvider

ROOT = Path(__file__).resolve().parents[1]
RESULT_COUNT = re.compile(r"Produced (\d+) structured result")


def _fixture() -> dict:
    return json.loads(
        (ROOT / "examples/synthetic_company.json").read_text(encoding="utf-8")
    )


class CountingProvider(MockNarrativeProvider):
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, pages, document, year):
        self.calls += 1
        return super().extract(pages, document, year)


def _run(provider=None):
    data = _fixture()
    agent = FinancialRiskAgent(ROOT, provider) if provider else FinancialRiskAgent(ROOT)
    return agent.run(
        data["company"],
        data["fiscal_year"],
        data["current"],
        data["previous"],
        {int(key): value for key, value in data["pages"].items()},
    )


def _reported_count(state, tool: str) -> int:
    entry = next(item for item in state.trace if item.tool == tool)
    match = RESULT_COUNT.search(entry.summary)
    assert match, f"{tool} trace summary is not a result count: {entry.summary!r}"
    return int(match.group(1))


def test_trace_reports_the_rule_set_the_decision_actually_used():
    """The Agent used to evaluate rules on a thinner fact set than the assessment.

    The trace then reported a smaller signal count than the decision was built from,
    so the published audit trail described a different computation than the one that
    produced the answer.
    """
    state = _run()
    assert state.assessment is not None
    assert _reported_count(state, "risk_rules") == len(
        state.assessment["triggered_rules"]
    )


def test_trace_reports_the_model_results_the_assessment_actually_contains():
    """The trace count is the number of model evaluations produced, which is what
    the assessment carries. Applicability is not collapsed into this number: each
    model reports its own `output` and `applicability` inside the assessment, so a
    reader can tell "evaluated" from "applicable"."""
    state = _run()
    assert state.assessment is not None
    assert _reported_count(state, "traditional_models") == len(
        state.assessment["models"]
    )
    assert len(state.assessment["models"]) == 4


def test_narrative_extraction_runs_exactly_once_per_analysis():
    """The Agent and the deterministic assessment each used to call the provider,
    producing two claim sets that fed `contradictions` and `disclosure_tensions`."""
    provider = CountingProvider()
    state = _run(provider)
    assert state.assessment is not None
    assert provider.calls == 1


def test_claim_classification_cannot_contradict_the_contradiction_list():
    """A claim used to be classifiable as a material contradiction by one path and
    as a non-issue by the other, inside a single API response."""
    state = _run()
    assert state.assessment is not None
    evaluations = state.assessment["claim_consistency_evaluations"]
    material = [
        item
        for item in evaluations
        if item["classification"] == "MATERIAL_CONTRADICTION"
    ]
    assert len(material) == len(state.assessment["contradictions"])


def test_disclosure_tensions_are_produced_on_the_same_claim_set():
    state = _run()
    assert state.assessment is not None
    assert len(state.assessment["disclosure_tensions"]) == len(
        state.assessment["claim_consistency_evaluations"]
    )


def test_outward_score_is_the_score_the_decision_was_derived_from():
    """`overall_score` used to be a weighted aggregate while the decision came from
    hierarchical escalation, so the Workbench could show `N/A` beside `PASS`."""
    state = _run()
    assert state.assessment is not None
    assert state.assessment["overall_score"] == state.risk_score
    assert "legacy_weighted_score" in state.assessment


def test_fusion_component_version_tracks_the_decision_policy():
    """A hand-written fusion version string could not detect a change to the
    escalation parameters, so a parameter change was misreported as output drift
    rather than as a component-version mismatch."""
    state = _run()
    assert state.analysis_snapshot is not None
    versions = state.analysis_snapshot["component_versions"]
    policy_hash = canonical_hash(
        json.loads(
            (ROOT / "config" / "decision_policy.json").read_text(encoding="utf-8")
        )
    )
    assert versions["decision_policy"] == policy_hash
    assert versions["fusion"].endswith(policy_hash[:12])


def test_a_missing_dimension_is_never_read_as_a_zero_score():
    """`interaction_aware` used `scores.get(dimension, 0)`, so an unknown dimension
    was evaluated as "no interaction" - that is, as safe."""
    partial = interaction_aware({"liquidity": 70}, 0.8, 0.9)
    assert "CLAIM_CONTEXT_INCOMPLETE" in partial.reason_codes
    complete = interaction_aware({"liquidity": 70, "solvency_leverage": 60}, 0.8, 0.9)
    assert "CLAIM_CONTEXT_INCOMPLETE" not in complete.reason_codes
