from pathlib import Path

from finrisk.agent import FinancialRiskAgent
from finrisk.llm import MockNarrativeProvider
from finrisk.pipeline import FinRiskPipeline

ROOT = Path(__file__).resolve().parents[1]


def test_agent_registry_reuses_loaded_pipeline_configuration(monkeypatch):
    """A request must not reconstruct the pipeline or reread static config files."""
    pipeline = FinRiskPipeline(ROOT, MockNarrativeProvider())
    agent = FinancialRiskAgent(ROOT, pipeline.provider, pipeline)

    assert agent.pipeline is pipeline

    def unexpected_read(*_args, **_kwargs):
        raise AssertionError("static configuration was reread after startup")

    monkeypatch.setattr(Path, "read_text", unexpected_read)
    assessment = agent.tools.call(
        "risk_assessment",
        company="Configuration reuse",
        year=2025,
        current={},
    )

    assert assessment.company == "Configuration reuse"
    assert agent.component_versions()["rules"]
