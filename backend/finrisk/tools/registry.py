from __future__ import annotations

from pathlib import Path

from ..agent.tool_registry import ToolRegistry, ToolSpec
from ..contradictions import detect_contradictions
from ..enterprise.applicability import applicability_report, enforce_applicability
from ..evidence import EvidenceVerifier
from ..llm import NarrativeProvider
from ..metrics import calculate_metrics
from ..models import altman_z, beneish_m, ohlson_o, piotroski_f
from ..pipeline import FinRiskPipeline
from ..rules import RuleEngine
from .ingestion import ingest_pdf, ingest_xbrl


def build_tool_registry(root: Path, provider: NarrativeProvider) -> ToolRegistry:
    registry = ToolRegistry()
    pipeline = FinRiskPipeline(root, provider)
    rules = RuleEngine.from_file(root / "rules" / "rules.json")
    verifier = EvidenceVerifier()
    registry.register(
        ToolSpec(
            "pdf_extraction",
            "Page-aware PDF extraction",
            ingest_pdf,
            ("path", "document", "fiscal_year"),
        )
    )
    registry.register(
        ToolSpec(
            "xbrl_extraction",
            "SEC XBRL normalization with provenance",
            ingest_xbrl,
            ("companyfacts",),
        )
    )
    registry.register(
        ToolSpec(
            "normalization",
            "Typed numeric normalization",
            lambda value, **_: float(value),
            ("value",),
        )
    )
    registry.register(
        ToolSpec(
            "financial_metrics",
            "Deterministic ratios and trends",
            lambda current, year, previous=None, **_: calculate_metrics(
                current, year, previous
            ),
            ("current", "year"),
        )
    )
    registry.register(
        ToolSpec(
            "traditional_models",
            "Applicability-gated financial models",
            lambda current, previous=None, entity_type="industrial", **_: _models(
                current, previous, entity_type
            ),
            ("current",),
        )
    )
    registry.register(
        ToolSpec(
            "risk_rules",
            "Configured expert rules",
            lambda facts, **_: rules.evaluate(facts),
            ("facts",),
        )
    )
    registry.register(
        ToolSpec(
            "narrative_evidence",
            "Structured narrative extraction and quote verification",
            lambda pages, document, year, **_: _claims(
                provider, verifier, pages, document, year
            ),
            ("pages", "document", "year"),
        )
    )
    registry.register(
        ToolSpec(
            "contradiction_detection",
            "Narrative-numeric consistency checks",
            lambda claims, facts, **_: detect_contradictions(claims, facts),
            ("claims", "facts"),
        )
    )
    registry.register(
        ToolSpec(
            "period_comparison",
            "Period coverage validation",
            lambda current, previous, **_: {
                "comparable_fields": sorted(set(current) & set(previous)),
                "previous_available": bool(previous),
            },
            ("current", "previous"),
        )
    )
    registry.register(
        ToolSpec(
            "risk_assessment",
            "Evidence-linked deterministic assessment",
            lambda **kwargs: pipeline.assess(**kwargs),
            ("company", "year", "current"),
        )
    )
    registry.register(
        ToolSpec(
            "claim_verification",
            "Material claim evidence gate",
            lambda conclusions, **_: conclusions,
            ("conclusions",),
        )
    )
    registry.register(
        ToolSpec(
            "evidence_retrieval",
            "Retrieve page evidence",
            lambda pages, page, **_: pages.get(page),
            ("pages", "page"),
        )
    )
    registry.register(
        ToolSpec(
            "missing_data_detection",
            "Identify missing required values",
            lambda current, required, **_: sorted(
                key for key in required if current.get(key) is None
            ),
            ("current", "required"),
        )
    )
    registry.register(
        ToolSpec(
            "model_applicability",
            "Expose model scope and missing inputs",
            lambda industry, facts, **_: applicability_report(industry, facts),
            ("industry", "facts"),
        )
    )
    registry.register(
        ToolSpec(
            "risk_signal_calculation",
            "Calculate configured risk signals",
            lambda facts, **_: rules.evaluate(facts),
            ("facts",),
        )
    )
    return registry


def _models(current: dict, previous: dict | None, entity_type: str):
    metrics = calculate_metrics(current, 0, previous)
    inputs = current | {
        "working_capital": metrics["working_capital"].value,
        "ebit": current.get("ebit", current.get("operating_income")),
    }
    results = [
        altman_z(
            inputs,
            "bank"
            if entity_type in {"bank", "financial_institution"}
            else "public_manufacturer",
        )
    ]
    if previous:
        results += [beneish_m(current, previous), piotroski_f(current, previous)]
    results += [ohlson_o(inputs)]
    return enforce_applicability(results, entity_type, inputs | current)


def _claims(provider, verifier, pages, document, year):
    accepted = []
    for claim in provider.extract(pages, document, year):
        evidence = verifier.verify(claim.evidence, pages)
        if evidence.verified:
            claim.evidence = evidence
            accepted.append(claim)
    return accepted
