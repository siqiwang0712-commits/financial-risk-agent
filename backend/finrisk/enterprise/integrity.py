from __future__ import annotations

from enum import StrEnum


class DecisionReasonCode(StrEnum):
    SEVERE_VERIFIED_SIGNAL = "SEVERE_VERIFIED_SIGNAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CLAIM_CONTEXT_INCOMPLETE = "CLAIM_CONTEXT_INCOMPLETE"
    HIGH_MODEL_DISAGREEMENT = "HIGH_MODEL_DISAGREEMENT"
    UNVALIDATED_RELIABILITY = "UNVALIDATED_RELIABILITY"
    CRITICAL_DIMENSION_ESCALATION = "CRITICAL_DIMENSION_ESCALATION"
    AGGREGATE_CRITICAL_SCORE = "AGGREGATE_CRITICAL_SCORE"
    DUPLICATE_EVIDENCE_SUPPRESSED = "DUPLICATE_EVIDENCE_SUPPRESSED"


class CalibrationStatus(StrEnum):
    UNCALIBRATED = "UNCALIBRATED"
    CALIBRATED_INTERNAL = "CALIBRATED_INTERNAL"
    VALIDATED_EXTERNAL = "VALIDATED_EXTERNAL"


def epistemic_summary(
    *,
    evidence_coverage: float,
    evidence_quality: float,
    disagreement: float,
    reliability: float | None = None,
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED,
) -> dict:
    """Keep epistemic quantities distinct; reliability is absent until calibrated."""
    if calibration_status is CalibrationStatus.UNCALIBRATED:
        reliability = None
    return {
        "evidence_coverage": round(evidence_coverage, 3),
        "evidence_quality": round(evidence_quality, 3),
        "model_disagreement": round(disagreement, 3),
        "reliability": None if reliability is None else round(reliability, 3),
        "calibration_status": calibration_status.value,
        "probability": None,
    }
