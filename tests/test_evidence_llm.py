from finrisk.contradictions import detect_contradictions
from finrisk.domain import Evidence, NarrativeClaim
from finrisk.evidence import EvidenceVerifier
from finrisk.llm import MockNarrativeProvider


def test_evidence_verification_rejects_hallucination():
    v = EvidenceVerifier()
    pages = {2: "Liquidity remains strong despite market volatility."}
    assert v.verify(
        Evidence("x", 2, "Liquidity remains strong", 2025, 0.9), pages
    ).verified
    assert not v.verify(
        Evidence("x", 2, "Debt covenant was breached", 2025, 0.9), pages
    ).verified
    normalized = v.verify(
        Evidence("x", 2, "Liquidity remains strong", 2025, 0.9), pages
    )
    assert (
        normalized.source == "x"
        and normalized.quote == "Liquidity remains strong"
        and normalized.period == "2025"
    )


def test_mock_claim_and_contradiction():
    pages = {4: "Liquidity remains strong."}
    claims = MockNarrativeProvider().extract(pages, "x", 2025)
    claim = NarrativeClaim(
        claims[0].claim,
        claims[0].risk_category,
        Evidence("x", 4, claims[0].claim, 2025, verification_status="verified"),
        "positive",
    )
    out = detect_contradictions(
        [claim],
        {
            "cash_growth": -0.3,
            "current_ratio": 0.8,
            "short_term_debt_growth": 0.3,
        },
    )
    assert len(out) == 1 and "not evidence of fraud" in out[0].interpretation


def test_negated_going_concern_is_not_extracted_as_risk():
    claims = MockNarrativeProvider().extract(
        {1: "There is no substantial doubt about going concern."}, "x", 2025
    )
    assert not claims
