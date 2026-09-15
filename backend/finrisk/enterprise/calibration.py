from __future__ import annotations

import math

from .integrity import CalibrationStatus, DecisionReasonCode


def brier_score(labels: list[int], probabilities: list[float]) -> float:
    _validate(labels, probabilities)
    return round(sum((p - y) ** 2 for y, p in zip(labels, probabilities, strict=True)) / len(labels), 6)


def reliability_diagram(labels: list[int], probabilities: list[float], bins: int = 10) -> list[dict]:
    _validate(labels, probabilities)
    if bins < 1:
        raise ValueError("bins must be positive")
    output = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(y, p) for y, p in zip(labels, probabilities, strict=True) if low <= p <= high and (p < high or index == bins - 1)]
        if members:
            output.append({"bin": index, "count": len(members), "mean_probability": round(sum(p for _, p in members) / len(members), 6), "observed_rate": round(sum(y for y, _ in members) / len(members), 6)})
    return output


def expected_calibration_error(labels: list[int], probabilities: list[float], bins: int = 10) -> float:
    diagram = reliability_diagram(labels, probabilities, bins)
    return round(sum(row["count"] / len(labels) * abs(row["mean_probability"] - row["observed_rate"]) for row in diagram), 6)


def risk_coverage_curve(labels: list[int], probabilities: list[float], reliabilities: list[float]) -> list[dict]:
    if not (len(labels) == len(probabilities) == len(reliabilities)) or not labels:
        raise ValueError("aligned non-empty inputs are required")
    _validate(labels, probabilities)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in reliabilities
    ):
        raise ValueError("reliabilities must be finite and within [0, 1]")
    output = []
    for threshold in sorted(set(reliabilities)):
        selected = [(y, p) for y, p, r in zip(labels, probabilities, reliabilities, strict=True) if r >= threshold]
        errors = sum((p >= 0.5) != bool(y) for y, p in selected)
        output.append({"reliability_threshold": threshold, "coverage": round(len(selected) / len(labels), 6), "selective_error": round(errors / len(selected), 6) if selected else None})
    return output


def selective_decision(proposed: str, coverage: float, reliability: float | None, disagreement: float, policy: dict[str, float], calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED) -> dict:
    if proposed not in {"PASS", "FLAG", "REVIEW", "ABSTAIN"}:
        raise ValueError("unknown proposed decision")
    numeric = [coverage, disagreement] + ([] if reliability is None else [reliability])
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in numeric
    ):
        raise ValueError("coverage, reliability and disagreement must be within [0, 1]")
    allowed = {"minimum_coverage", "minimum_reliability", "maximum_disagreement"}
    unknown = set(policy) - allowed
    if unknown:
        raise ValueError(f"unknown selective policy keys: {sorted(unknown)}")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in policy.values()
    ):
        raise ValueError("selective policy thresholds must be within [0, 1]")
    failures = []
    if coverage < policy.get("minimum_coverage", 0.5):
        failures.append("LOW_COVERAGE")
    if calibration_status is CalibrationStatus.UNCALIBRATED:
        reliability = None
        failures.append(DecisionReasonCode.UNVALIDATED_RELIABILITY.value)
    elif reliability is None:
        failures.append("MISSING_CALIBRATED_RELIABILITY")
    elif reliability < policy.get("minimum_reliability", 0.6):
        failures.append("LOW_RELIABILITY")
    if disagreement >= policy.get("maximum_disagreement", 0.45):
        failures.append(DecisionReasonCode.HIGH_MODEL_DISAGREEMENT.value)
    decision = "ABSTAIN" if {"LOW_COVERAGE", DecisionReasonCode.UNVALIDATED_RELIABILITY.value, "MISSING_CALIBRATED_RELIABILITY"} & set(failures) else "REVIEW" if failures else proposed
    return {"decision": decision, "proposed_decision": proposed, "failure_reasons": failures, "automation_allowed": not failures, "reliability": reliability, "calibration_status": calibration_status.value}


def _validate(labels: list[int], probabilities: list[float]) -> None:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("aligned non-empty labels and probabilities are required")
    if any(isinstance(label, bool) or label not in {0, 1} for label in labels) or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in probabilities
    ):
        raise ValueError("labels must be binary and probabilities within [0, 1]")
