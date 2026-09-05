from __future__ import annotations

from dataclasses import asdict, dataclass

from ..domain import Evidence, NarrativeClaim


@dataclass(frozen=True)
class DisclosureTension:
    claim: str
    supporting_evidence: list[str]
    opposing_evidence: list[str]
    context: str
    classification: str
    confidence: float
    source: Evidence

    def to_dict(self):
        return asdict(self)


def classify_tension(
    claim: NarrativeClaim, supporting: list[str], opposing: list[str], context: str = ""
) -> DisclosureTension:
    verified = claim.evidence.verification_status == "verified"
    if not verified:
        classification, confidence = "Insufficient Evidence", 0.1
    elif len(opposing) >= 2 and not supporting:
        classification, confidence = "Material Contradiction", 0.9
    elif opposing and supporting:
        classification, confidence = "Context-dependent", 0.65
    elif opposing:
        classification, confidence = "Tension", 0.75
    elif len(supporting) >= 2:
        classification, confidence = "Supported", 0.85
    elif supporting:
        classification, confidence = "Weakly Supported", 0.6
    else:
        classification, confidence = "Insufficient Evidence", 0.25
    return DisclosureTension(
        claim.claim,
        supporting,
        opposing,
        context,
        classification,
        confidence,
        claim.evidence,
    )
