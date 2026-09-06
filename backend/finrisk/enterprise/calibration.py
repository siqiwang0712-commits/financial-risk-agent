from __future__ import annotations


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
    output = []
    for threshold in sorted(set(reliabilities)):
        selected = [(y, p) for y, p, r in zip(labels, probabilities, reliabilities, strict=True) if r >= threshold]
        errors = sum((p >= 0.5) != bool(y) for y, p in selected)
        output.append({"reliability_threshold": threshold, "coverage": round(len(selected) / len(labels), 6), "selective_error": round(errors / len(selected), 6) if selected else None})
    return output


def selective_decision(proposed: str, coverage: float, reliability: float | None, disagreement: float, policy: dict[str, float]) -> dict:
    failures = []
    if coverage < policy.get("minimum_coverage", 0.5):
        failures.append("LOW_COVERAGE")
    if reliability is None:
        failures.append("UNCALIBRATED_RELIABILITY")
    elif reliability < policy.get("minimum_reliability", 0.6):
        failures.append("LOW_RELIABILITY")
    if disagreement >= policy.get("maximum_disagreement", 0.45):
        failures.append("HIGH_DISAGREEMENT")
    decision = "ABSTAIN" if {"LOW_COVERAGE", "UNCALIBRATED_RELIABILITY"} & set(failures) else "REVIEW" if failures else proposed
    return {"decision": decision, "proposed_decision": proposed, "failure_reasons": failures, "automation_allowed": not failures}


def _validate(labels: list[int], probabilities: list[float]) -> None:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("aligned non-empty labels and probabilities are required")
    if any(label not in {0, 1} for label in labels) or any(not 0 <= value <= 1 for value in probabilities):
        raise ValueError("labels must be binary and probabilities within [0, 1]")
