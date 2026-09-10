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
    reason_code: str = "UNVALIDATED_RELIABILITY"
    evidence_sufficiency: str = "unknown"

    def to_dict(self):
        return asdict(self)


def classify_tension(
    claim: NarrativeClaim,
    supporting: list[str],
    opposing: list[str],
    context: str = "",
    evidence_sufficiency: str = "complete",
    reason_code: str = "UNVALIDATED_RELIABILITY",
) -> DisclosureTension:
    verified = claim.evidence.verification_status == "verified"
    if evidence_sufficiency != "complete":
        classification, confidence = "Insufficient Evidence", 0.0
    elif not verified:
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
        reason_code,
        evidence_sufficiency,
    )
