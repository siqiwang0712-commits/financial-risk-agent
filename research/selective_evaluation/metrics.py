"""Mathematically explicit metrics for selective decision evaluation."""

from __future__ import annotations

import math
from collections.abc import Iterable


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def evaluate_decisions(
    labels: Iterable[int],
    decisions: Iterable[str],
    *,
    support_verified: Iterable[bool] | None = None,
    in_reference: Iterable[bool] | None = None,
) -> dict:
    """Evaluate issued PASS/FLAG decisions versus REVIEW/ABSTAIN withholding.

    Selective error is the fraction of authorized decisions whose PASS/FLAG class is wrong.
    Coverage and authorized-decision rate are the authorized fraction of all observations.
    Unsupported and out-of-reference authorization rates use all observations as denominator;
    they are ``NOT_ESTIMABLE`` when the corresponding annotations are absent.
    """

    y = [int(value) for value in labels]
    d = [str(value) for value in decisions]
    if len(y) != len(d) or not y:
        raise ValueError("labels and decisions must be equally sized and non-empty")
    if any(value not in {0, 1} for value in y):
        raise ValueError("labels must be binary")
    if any(value not in {"PASS", "FLAG", "REVIEW", "ABSTAIN"} for value in d):
        raise ValueError("decision is outside PASS/FLAG/REVIEW/ABSTAIN")

    authorized = [index for index, value in enumerate(d) if value in {"PASS", "FLAG"}]
    errors = sum((d[index] == "FLAG") != bool(y[index]) for index in authorized)
    reviews = sum(value == "REVIEW" for value in d)
    abstentions = sum(value == "ABSTAIN" for value in d)
    result = {
        "n": len(y),
        "authorized": len(authorized),
        "coverage": _rate(len(authorized), len(y)),
        "authorized_decision_rate": _rate(len(authorized), len(y)),
        "selective_error": _rate(errors, len(authorized)),
        "erroneous_authorized_decision_rate": _rate(errors, len(y)),
        "review_rate": _rate(reviews, len(y)),
        "abstention_rate": _rate(abstentions, len(y)),
    }
    if support_verified is None:
        result["unsupported_authorized_decision_rate"] = "NOT_ESTIMABLE"
    else:
        support = list(support_verified)
        if len(support) != len(y):
            raise ValueError("support annotations must align with labels")
        if any(type(value) is not bool for value in support):
            raise ValueError("support annotations must be booleans")
        result["unsupported_authorized_decision_rate"] = _rate(
            sum(not support[index] for index in authorized), len(y)
        )
    if in_reference is None:
        result["out_of_reference_authorization_rate"] = "NOT_ESTIMABLE"
    else:
        reference = list(in_reference)
        if len(reference) != len(y):
            raise ValueError("reference annotations must align with labels")
        if any(type(value) is not bool for value in reference):
            raise ValueError("reference annotations must be booleans")
        result["out_of_reference_authorization_rate"] = _rate(
            sum(not reference[index] for index in authorized), len(y)
        )
    return result


def risk_coverage_curve(labels: Iterable[int], scores: Iterable[float]) -> list[dict]:
    """Return deterministic confidence-ranked error/coverage points.

    Confidence is ``abs(score - 0.5)``. Ties are resolved by original row order. Each point
    authorizes the first *k* observations, maps score >= 0.5 to FLAG, and reports cumulative
    selective error. This is an experiment-specific diagnostic, not a safety guarantee.
    """

    y = [int(value) for value in labels]
    s = [float(value) for value in scores]
    if len(y) != len(s) or not y:
        raise ValueError("labels and scores must be equally sized and non-empty")
    if any(value not in {0, 1} for value in y):
        raise ValueError("labels must be binary")
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in s):
        raise ValueError("scores must be finite values in [0, 1]")
    order = sorted(range(len(y)), key=lambda index: (-abs(s[index] - 0.5), index))
    errors = 0
    points = []
    for count, index in enumerate(order, start=1):
        errors += (s[index] >= 0.5) != bool(y[index])
        points.append(
            {
                "authorized": count,
                "coverage": count / len(y),
                "selective_error": errors / count,
                "score_confidence_threshold": abs(s[index] - 0.5),
            }
        )
    return points
