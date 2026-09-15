from __future__ import annotations

from dataclasses import asdict, dataclass

from ..contradictions import ClaimConsistencyReasonCode
from ..domain import Evidence, NarrativeClaim

# The closed vocabulary of `evidence_sufficiency`.
#
# The field defaulted to `"unknown"`, a third value no producer ever emitted, so
# the declared type said one thing and every real payload said another. The set
# is validated on construction: an unrecognised value is a programming error, not
# a state to be silently classified as "insufficient".
EVIDENCE_SUFFICIENCY_VALUES: tuple[str, ...] = ("complete", "incomplete_context")

# The reason code a classification implies when the caller does not supply one.
# This used to default to `"UNVALIDATED_RELIABILITY"` - a *decision* reason code
# from `enterprise.integrity.DecisionReasonCode`, i.e. a value from a different
# vocabulary that no claim-consistency producer can emit.
CLASSIFICATION_REASON_CODES: dict[str, ClaimConsistencyReasonCode] = {
    "Insufficient Evidence": ClaimConsistencyReasonCode.INSUFFICIENT_EVIDENCE,
    "Material Contradiction": ClaimConsistencyReasonCode.SEVERE_VERIFIED_SIGNAL,
    "Context-dependent": ClaimConsistencyReasonCode.PARTIAL_NUMERIC_TENSION,
    "Tension": ClaimConsistencyReasonCode.PARTIAL_NUMERIC_TENSION,
    "Supported": ClaimConsistencyReasonCode.NO_ADVERSE_CONFLICT,
    "Weakly Supported": ClaimConsistencyReasonCode.NO_ADVERSE_CONFLICT,
}


@dataclass(frozen=True)
class DisclosureTension:
    claim: str
    supporting_evidence: list[str]
    opposing_evidence: list[str]
    context: str
    classification: str
    confidence: float
    source: Evidence
    # `ClaimConsistencyReasonCode`, not `DecisionReasonCode`: see that enum for
    # why the two vocabularies are separate.
    reason_code: str = ClaimConsistencyReasonCode.CLAIM_CONTEXT_INCOMPLETE.value
    evidence_sufficiency: str = "complete"

    def to_dict(self):
        return asdict(self)


def classify_tension(
    claim: NarrativeClaim,
    supporting: list[str],
    opposing: list[str],
    context: str = "",
    evidence_sufficiency: str = "complete",
    reason_code: str | None = None,
) -> DisclosureTension:
    if evidence_sufficiency not in EVIDENCE_SUFFICIENCY_VALUES:
        raise ValueError(
            f"evidence_sufficiency must be one of {list(EVIDENCE_SUFFICIENCY_VALUES)}, "
            f"got {evidence_sufficiency!r}"
        )
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
    resolved_reason = ClaimConsistencyReasonCode(
        reason_code
        if reason_code is not None
        else CLASSIFICATION_REASON_CODES[classification].value
    ).value
    return DisclosureTension(
        claim.claim,
        supporting,
        opposing,
        context,
        classification,
        confidence,
        claim.evidence,
        resolved_reason,
        evidence_sufficiency,
    )
