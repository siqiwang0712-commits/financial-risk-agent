from pathlib import Path

from finrisk.agent import FinancialRiskAgent
from finrisk.llm import NarrativeProvider

ROOT = Path(__file__).resolve().parents[1]


class TimeoutProvider(NarrativeProvider):
    prompt_version = "timeout-test"

    def extract(self, pages, document, fiscal_year):
        raise TimeoutError("provider deadline exceeded")


def test_external_failure_matrix_llm_timeout_degrades_to_review():
    state = FinancialRiskAgent(ROOT, TimeoutProvider()).run(
        "Failure Co",
        2025,
        {"current_assets": 80, "current_liabilities": 100, "cash": 10},
        pages={1: "Liquidity remains strong."},
    )
    assert state.status == "REVIEW_REQUIRED"
    assert state.decision == "REVIEW"
    assert state.assessment["failure_state"]["review_failures"] == ["llm_unavailable"]
    assert any("Narrative provider unavailable" in warning for warning in state.warnings)
