from __future__ import annotations

import math
from collections import defaultdict

REVIEW_STATES = {"pending", "reviewer_1", "reviewer_2", "adjudicated"}


def _validate_binary_labels(labels: list[int]) -> None:
    if any(isinstance(label, bool) or label not in {0, 1} for label in labels):
        raise ValueError("labels must contain only integer 0 or 1")


def _validate_feature_matrix(features: list[list[float]]) -> None:
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for row in features
        for value in row
    ):
        raise ValueError("features must contain only finite numeric values")


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


def inter_rater_agreement(
    reviewer_1: list[int | None], reviewer_2: list[int | None]
) -> dict:
    if len(reviewer_1) != len(reviewer_2):
        raise ValueError("reviewer labels must be aligned")
    pairs = [
        (first, second)
        for first, second in zip(reviewer_1, reviewer_2, strict=True)
        if first in {0, 1} and second in {0, 1}
    ]
    if not pairs:
        return {"n": 0, "observed_agreement": None, "cohen_kappa": None}
    observed = sum(first == second for first, second in pairs) / len(pairs)
    first_positive = sum(first == 1 for first, _ in pairs) / len(pairs)
    second_positive = sum(second == 1 for _, second in pairs) / len(pairs)
    expected = first_positive * second_positive + (1 - first_positive) * (
        1 - second_positive
    )
    kappa = None if expected == 1 else (observed - expected) / (1 - expected)
    return {
        "n": len(pairs),
        "observed_agreement": round(observed, 6),
        "cohen_kappa": None if kappa is None else round(kappa, 6),
    }


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
    if not features[0]:
        raise ValueError("training data must contain at least one feature")
    _validate_feature_matrix(features)
    _validate_binary_labels(labels)
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or iterations < 1
        or isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ValueError("iterations and learning rate must be positive and finite")
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
    weights = model.get("weights")
    intercept = model.get("intercept")
    if (
        not isinstance(weights, list)
        or not weights
        or isinstance(intercept, bool)
        or not isinstance(intercept, (int, float))
        or not math.isfinite(intercept)
        or any(len(row) != len(weights) for row in features)
    ):
        raise ValueError("model and feature dimensions must be aligned")
    _validate_feature_matrix([weights, *features])
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
    # `fit_logistic_baseline` rejects ragged input; this function did not, so
    # `[[]]` raised `TypeError` on `features[0]` and a short row raised
    # `IndexError` deep inside the loop.
    width = len(features[0])
    if width == 0 or any(len(row) != width for row in features):
        raise ValueError("features must be a non-empty rectangular matrix")
    _validate_feature_matrix(features)
    _validate_binary_labels(labels)
    best = None
    for feature in range(width):
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
    if len(labels) != len(probabilities):
        raise ValueError("aligned labels and probabilities are required")
    _validate_binary_labels(labels)
    if (
        isinstance(false_negative_cost, bool)
        or not isinstance(false_negative_cost, (int, float))
        or not math.isfinite(false_negative_cost)
        or false_negative_cost < 0
    ):
        raise ValueError("false-negative cost must be finite and non-negative")
    if any(
        probability is not None
        and (
            isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
        )
        for probability in probabilities
    ):
        raise ValueError("probabilities must be None or finite values within [0, 1]")
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
    decided_indices = [
        index for index, probability in enumerate(probabilities) if probability is not None
    ]
    # Only a decided sample has a predicted risk to order by. An abstention has no
    # prediction, so placing it on the risk scale asserts something the model did
    # not say: `None` was keyed to `-1`, which sorts last in a descending ranking,
    # so every abstention was reported as *least* risky and would never be
    # reviewed -- the opposite of what abstaining is for. They are returned in
    # their own list instead of being silently ranked.
    ranking = sorted(
        decided_indices, key=lambda index: probabilities[index], reverse=True
    )
    abstained = [
        index for index, probability in enumerate(probabilities) if probability is None
    ]
    return {
        "coverage": len(decided) / len(labels) if labels else 0.0,
        "false_negative_cost": false_negatives * false_negative_cost + false_positives,
        "risk_ranking": ranking,
        "abstained": abstained,
    }


def calibration_curve(
    labels: list[int], probabilities: list[float], bins: int = 10
) -> list[dict]:
    if len(labels) != len(probabilities):
        raise ValueError("aligned labels and probabilities are required")
    if bins < 1:
        raise ValueError("bins must be >= 1")
    # A probability outside [0, 1] used to satisfy no bin's membership test and
    # vanish, so the curve silently omitted rows instead of reporting them.
    # `evaluation.expected_calibration_error` already rejects both of these; the
    # two same-purpose helpers now agree on when input is invalid.
    _validate_binary_labels(labels)
    if any(
        isinstance(probability, bool)
        or not isinstance(probability, (int, float))
        or not math.isfinite(probability)
        or not 0 <= probability <= 1
        for probability in probabilities
    ):
        raise ValueError("probabilities must be within [0, 1]")
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
