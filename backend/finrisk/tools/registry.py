from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..agent.tool_registry import ToolRegistry, ToolSpec
from ..agent.verification import verify_conclusions
from ..contradictions import detect_contradictions
from ..enterprise.applicability import applicability_report, enforce_applicability
from ..evidence import EvidenceVerifier, claim_is_grounded
from ..llm import NarrativeProvider
from ..metrics import calculate_metrics
from ..models import altman_z, beneish_m, ohlson_o, piotroski_f
from ..pipeline import FinRiskPipeline
from .ingestion import ingest_pdf, ingest_xbrl


def build_tool_registry(
    root: Path,
    provider: NarrativeProvider,
    pipeline: FinRiskPipeline | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    pipeline = pipeline or FinRiskPipeline(root, provider)
    rules = pipeline.rules
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
            lambda current, year, previous=None, entity_type="industrial", **_: _models(
                current, year, previous, entity_type
            ),
            ("current", "year"),
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
            lambda conclusions, **_: _verify(conclusions),
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


def _verify(conclusions):
    """Real evidence gate.

    The registered handler used to be the identity function
    (`lambda conclusions, **_: conclusions`), so the "verification" tool could
    never reject anything. It now runs the actual gate and returns both the
    admitted subset and the rejection reasons.
    """
    accepted, warnings = verify_conclusions(conclusions)
    return {"accepted": accepted, "warnings": warnings}


def _models(current: dict, year: int, previous: dict | None, entity_type: str):
    metrics = calculate_metrics(current, year, previous)
    ebit = current.get("ebit")
    if ebit is None:
        ebit = current.get("operating_income")
    inputs = current | {
        "working_capital": metrics["working_capital"].value,
        "ebit": ebit,
    }
    results = [altman_z(inputs, entity_type)]
    if previous:
        results += [beneish_m(current, previous), piotroski_f(current, previous)]
    results += [ohlson_o(inputs)]
    return enforce_applicability(results, entity_type, inputs | current)


def _claims(provider, verifier, pages, document, year):
    """Extract once and verify once.

    Returns both the admitted subset and the complete verification list so the
    caller can hand both to the deterministic assessment, keeping
    `verified_claim_coverage`'s denominator (all extracted claims) intact while
    ensuring the provider is invoked exactly once per analysis.

    A claim is admitted only when its quotation is on the page *and* the free-text
    claim is supported by that quotation; a verified quote does not make an
    unrelated assertion true.
    """
    accepted, verifications = [], []
    for claim in provider.extract(pages, document, year):
        evidence = verifier.verify(claim.evidence, pages)
        if evidence.verified and not claim_is_grounded(
            claim.claim, evidence.source_text, pages.get(evidence.page, "")
        ):
            evidence = replace(
                evidence,
                verified=False,
                verification_status="unverified",
                confidence=min(evidence.confidence, 0.25),
            )
        verifications.append(evidence)
        if evidence.verified:
            claim.evidence = evidence
            accepted.append(claim)
    return {"accepted": accepted, "verifications": verifications}
