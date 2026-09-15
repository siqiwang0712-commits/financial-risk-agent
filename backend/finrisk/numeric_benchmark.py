from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

FEATURES = ("current_ratio", "debt_to_assets", "net_margin", "cfo_to_net_income", "fcf_margin", "revenue_growth", "total_debt_growth")


def _usable(value: Any) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        return None
    return float(value)


def ratio_risk_score(metrics: dict[str, float | None]) -> float | None:
    checks = [
        ("current_ratio", lambda value: value < 1.0),
        ("debt_to_assets", lambda value: value > 0.60),
        ("net_margin", lambda value: value < 0),
        ("cfo_to_net_income", lambda value: value < 0.8),
        ("fcf_margin", lambda value: value < 0),
    ]
    observed = []
    for name, test in checks:
        value = _usable(metrics.get(name))
        if value is None:
            continue
        net_income = _usable(metrics.get("net_income"))
        if name == "cfo_to_net_income" and net_income is not None and net_income <= 0:
            continue
        observed.append(float(test(value)))
    return sum(observed) / len(observed) if observed else None


def temporal_risk_score(metrics: dict[str, float | None]) -> float | None:
    base = ratio_risk_score(metrics)
    adverse = 0
    observed = 0
    for name, test in (
        ("revenue_growth", lambda value: value <= -0.10),
        ("operating_cash_flow_growth", lambda value: value <= -0.25),
        ("total_debt_growth", lambda value: value >= 0.20),
        ("cash_growth", lambda value: value <= -0.20),
    ):
        value = _usable(metrics.get(name))
        if value is not None:
            observed += 1
            adverse += int(test(value))
    if base is None:
        return adverse / observed if observed else None
    return base if not observed else min(1.0, 0.75 * base + 0.25 * adverse / observed)


class LogisticBaseline:
    """Small deterministic logistic baseline; preprocessing is fitted on train only."""

    def __init__(self, learning_rate: float = 0.1, iterations: int = 800):
        if (
            isinstance(learning_rate, bool)
            or not isinstance(learning_rate, (int, float))
            or not math.isfinite(learning_rate)
            or learning_rate <= 0
            or isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or iterations < 1
        ):
            raise ValueError("learning rate and iterations must be positive and finite")
        self.learning_rate = learning_rate
        self.iterations = iterations
        self.means: list[float] = []
        self.scales: list[float] = []
        self.weights: list[float] = []

    @staticmethod
    def _raw(row: dict[str, Any]) -> list[float | None]:
        return [_usable(row.get("metrics", {}).get(name)) for name in FEATURES]

    def _matrix(self, rows: list[dict[str, Any]], fit: bool) -> list[list[float]]:
        raw = [self._raw(row) for row in rows]
        if fit:
            self.means = []
            self.scales = []
            for column in range(len(FEATURES)):
                values = [float(item[column]) for item in raw if item[column] is not None]
                mean = sum(values) / len(values) if values else 0.0
                variance = sum((value - mean) ** 2 for value in values) / len(values) if values else 0.0
                self.means.append(mean)
                self.scales.append(math.sqrt(variance) or 1.0)
        if not self.means:
            raise ValueError("baseline is not fitted")
        return [[1.0] + [((self.means[i] if value is None else float(value)) - self.means[i]) / self.scales[i] for i, value in enumerate(item)] for item in raw]

    def fit(self, rows: list[dict[str, Any]], labels: list[int]) -> LogisticBaseline:
        if (
            len(rows) != len(labels)
            or not rows
            or any(isinstance(label, bool) or label not in {0, 1} for label in labels)
            or len(set(labels)) < 2
        ):
            raise ValueError("logistic baseline requires aligned train rows with both classes")
        matrix = self._matrix(rows, fit=True)
        self.weights = [0.0] * len(matrix[0])
        for _ in range(self.iterations):
            gradient = [0.0] * len(self.weights)
            for features, label in zip(matrix, labels, strict=True):
                prediction = 1 / (1 + math.exp(-max(-30.0, min(30.0, sum(w * x for w, x in zip(self.weights, features, strict=True))))))
                for index, value in enumerate(features):
                    gradient[index] += (prediction - label) * value
            for index in range(len(self.weights)):
                self.weights[index] -= self.learning_rate * gradient[index] / len(matrix)
        return self

    def predict_scores(self, rows: list[dict[str, Any]]) -> list[float]:
        matrix = self._matrix(rows, fit=False)
        return [1 / (1 + math.exp(-max(-30.0, min(30.0, sum(w * x for w, x in zip(self.weights, features, strict=True)))))) for features in matrix]


def temporal_trajectories(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        grouped[row["ticker"]].append(row)
    result = []
    for ticker, rows in grouped.items():
        rows.sort(key=lambda row: row["fiscal_year"])
        if len(rows) < 2:
            continue
        points = [{"fiscal_year": row["fiscal_year"], "risk": temporal_risk_score(row["metrics"])} for row in rows]
        # `temporal_risk_score` returns `None` when a period has no usable inputs,
        # and `None - None` raised `TypeError` -- one incomplete period killed the
        # whole trajectory report. The delta is withheld (`None`) instead, which is
        # how this codebase represents "not computable".
        first, last = points[0]["risk"], points[-1]["risk"]
        result.append({
            "ticker": ticker,
            "points": points,
            "delta": None if first is None or last is None else last - first,
        })
    return result
