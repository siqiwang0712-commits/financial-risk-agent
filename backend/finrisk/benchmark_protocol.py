from __future__ import annotations

import math
from collections import defaultdict

REVIEW_STATES = {"pending", "reviewer_1", "reviewer_2", "adjudicated"}


def validate_company_year_manifest(rows: list[dict]) -> dict:
    required = {
        "observation_id",
        "company_id",
        "fiscal_year",
        "as_of_date",
        "split",
        "source_url",
        "source_hash",
        "review_status",
    }
    errors = []
    companies: dict[str, set[str]] = defaultdict(set)
    identifiers = set()
    for index, row in enumerate(rows):
        missing = required - set(row)
        if missing:
            errors.append(f"row {index}: missing {sorted(missing)}")
            continue
        if row["observation_id"] in identifiers:
            errors.append(f"row {index}: duplicate observation_id")
        identifiers.add(row["observation_id"])
        companies[row["company_id"]].add(row["split"])
        if row["review_status"] not in REVIEW_STATES:
            errors.append(f"row {index}: invalid review status")
        if (
            row.get("label_available_at")
            and row["label_available_at"] <= row["as_of_date"]
        ):
            errors.append(f"row {index}: possible future-label leakage")
    leaking = sorted(
        company for company, splits in companies.items() if len(splits) > 1
    )
    if leaking:
        errors.append(f"company-disjoint violation: {leaking}")
    return {
        "valid": not errors,
        "errors": errors,
        "company_disjoint": not leaking,
        "observation_count": len(rows),
    }


def adjudicate_label(
    review_1: int | None, review_2: int | None, adjudicated: int | None
) -> dict:
    if review_1 is None or review_2 is None:
        return {"status": "PENDING_DUAL_REVIEW", "label": None}
    if review_1 == review_2:
        return {"status": "DUAL_REVIEW_AGREEMENT", "label": review_1}
    if adjudicated is None:
        return {"status": "ADJUDICATION_REQUIRED", "label": None}
    return {"status": "ADJUDICATED", "label": adjudicated}


def fit_logistic_baseline(
    features: list[list[float]],
    labels: list[int],
    iterations: int = 400,
    rate: float = 0.05,
) -> dict:
    if (
        not features
        or len(features) != len(labels)
        or len({len(row) for row in features}) != 1
    ):
        raise ValueError("aligned rectangular training data required")
    weights = [0.0] * len(features[0])
    intercept = 0.0
    for _ in range(iterations):
        grad = [0.0] * len(weights)
        grad_intercept = 0.0
        for row, label in zip(features, labels, strict=True):
            probability = 1 / (
                1
                + math.exp(
                    -max(
                        -30,
                        min(
                            30,
                            intercept
                            + sum(w * x for w, x in zip(weights, row, strict=True)),
                        ),
                    )
                )
            )
            error = probability - label
            grad_intercept += error
            for index, value in enumerate(row):
                grad[index] += error * value
        scale = rate / len(labels)
        intercept -= scale * grad_intercept
        weights = [
            weight - scale * gradient
            for weight, gradient in zip(weights, grad, strict=True)
        ]
    return {"weights": weights, "intercept": intercept, "training_only": True}


def predict_logistic(model: dict, features: list[list[float]]) -> list[float]:
    return [
        1
        / (
            1
            + math.exp(
                -max(
                    -30,
                    min(
                        30,
                        model["intercept"]
                        + sum(
                            w * x for w, x in zip(model["weights"], row, strict=True)
                        ),
                    ),
                )
            )
        )
        for row in features
    ]


def fit_decision_stump(features: list[list[float]], labels: list[int]) -> dict:
    if not features or len(features) != len(labels):
        raise ValueError("aligned training data required")
    best = None
    for feature in range(len(features[0])):
        for threshold in sorted({row[feature] for row in features}):
            predictions = [int(row[feature] >= threshold) for row in features]
            errors = sum(
                prediction != label
                for prediction, label in zip(predictions, labels, strict=True)
            )
            candidate = (errors, feature, threshold)
            if best is None or candidate < best:
                best = candidate
    return {"feature": best[1], "threshold": best[2], "training_only": True}


def selective_metrics(
    labels: list[int],
    probabilities: list[float | None],
    false_negative_cost: float = 5.0,
) -> dict:
    decided = [
        (label, probability)
        for label, probability in zip(labels, probabilities, strict=True)
        if probability is not None
    ]
    predictions = [int(probability >= 0.5) for _, probability in decided]
    false_negatives = sum(
        label == 1 and prediction == 0
        for (label, _), prediction in zip(decided, predictions, strict=True)
    )
    false_positives = sum(
        label == 0 and prediction == 1
        for (label, _), prediction in zip(decided, predictions, strict=True)
    )
    ranking = sorted(
        range(len(probabilities)),
        key=lambda index: (
            probabilities[index] if probabilities[index] is not None else -1
        ),
        reverse=True,
    )
    return {
        "coverage": len(decided) / len(labels) if labels else 0.0,
        "false_negative_cost": false_negatives * false_negative_cost + false_positives,
        "risk_ranking": ranking,
    }


def calibration_curve(
    labels: list[int], probabilities: list[float], bins: int = 10
) -> list[dict]:
    result = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [
            (label, probability)
            for label, probability in zip(labels, probabilities, strict=True)
            if low <= probability < high or (index == bins - 1 and probability == 1)
        ]
        if members:
            result.append(
                {
                    "bin": index,
                    "count": len(members),
                    "mean_probability": sum(item[1] for item in members) / len(members),
                    "event_rate": sum(item[0] for item in members) / len(members),
                }
            )
    return result
