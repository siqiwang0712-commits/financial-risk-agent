import json
from pathlib import Path

import pytest
from finrisk.agent import AgentState, AgentStatus, FinancialRiskAgent
from finrisk.agent.planner import AgentPlanner
from finrisk.agent.tool_registry import ToolRegistry, ToolSpec
from finrisk.domain import Evidence, NarrativeClaim

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads(
        (ROOT / "examples/synthetic_company.json").read_text(encoding="utf-8")
    )


def test_agent_state_rejects_transition_after_terminal():
    state = AgentState("Example", 2025)
    state.transition(AgentStatus.COMPLETED)
    with pytest.raises(ValueError, match="terminal"):
        state.transition(AgentStatus.PLANNING)


def test_planner_and_tool_registry_are_explicit_and_typed():
    plan = AgentPlanner().plan(has_previous=True, has_pages=True)
    assert [step.tool for step in plan][-2:] == [
        "risk_assessment",
        "claim_verification",
    ]
    registry = ToolRegistry()
    registry.register(ToolSpec("echo", "test", lambda value: value, ("value",)))
    assert registry.call("echo", value=3) == 3
    with pytest.raises(KeyError, match="unknown tool"):
        registry.call("invented")
    with pytest.raises(ValueError, match="missing inputs"):
        registry.call("echo")


def test_end_to_end_agent_workflow_requires_review_on_contradiction():
    data = fixture()
    state = FinancialRiskAgent(ROOT).run(
        data["company"],
        data["fiscal_year"],
        data["current"],
        data["previous"],
        {int(k): v for k, v in data["pages"].items()},
    )
    assert state.status == AgentStatus.REVIEW_REQUIRED
    assert state.assessment and state.assessment["contradictions"]
    assert {item.tool for item in state.trace} >= {
        "financial_metrics",
        "traditional_models",
        "risk_rules",
        "narrative_evidence",
        "contradiction_detection",
        "risk_assessment",
        "claim_verification",
    }
    assert state.conclusions
    assert all(conclusion.evidence for conclusion in state.conclusions)
    assert state.evidence_coverage != state.confidence


def test_agent_abstains_when_dimension_coverage_is_insufficient():
    state = FinancialRiskAgent(ROOT).run("Sparse Co", 2025, {"cash": 10})
    assert state.status == AgentStatus.INSUFFICIENT_EVIDENCE
    assert state.risk_score is None
    assert any("withheld" in note for note in state.reflection)


class HallucinatingProvider:
    def extract(self, pages, document, year):
        return [
            NarrativeClaim(
                "A covenant was breached",
                "solvency",
                Evidence(document, 1, "A covenant was breached", year, 0.99),
                "negative",
            )
        ]


class MalformedProvider:
    def extract(self, pages, document, year):
        raise ValueError("malformed structured LLM output")


def test_hallucinated_claim_is_rejected_before_contradiction():
    data = fixture()
    state = FinancialRiskAgent(ROOT, HallucinatingProvider()).run(
        "Example",
        2025,
        data["current"],
        data["previous"],
        {1: "No covenant disclosure exists."},
    )
    assert state.assessment is not None
    assert state.assessment["contradictions"] == []


def test_malformed_provider_preserves_numeric_result_but_requires_review():
    data = fixture()
    state = FinancialRiskAgent(ROOT, MalformedProvider()).run(
        "Example", 2025, data["current"], pages={1: "text"}
    )
    assert state.status == AgentStatus.REVIEW_REQUIRED
    assert state.decision == "REVIEW"
    assert "malformed structured LLM output" in state.warnings[0]
    assert state.assessment["failure_state"]["review_failures"] == [
        "llm_unavailable"
    ]
