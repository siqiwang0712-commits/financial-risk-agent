import pytest
from finrisk.numeric_benchmark import (
    LogisticBaseline,
    ratio_risk_score,
    temporal_risk_score,
    temporal_trajectories,
)


def test_numeric_scores_are_missing_aware_and_temporal():
    assert ratio_risk_score({}) is None
    safe = {"current_ratio": 2.0, "debt_to_assets": 0.2, "net_margin": 0.2, "cfo_to_net_income": 1.1, "fcf_margin": 0.1}
    adverse = {**safe, "revenue_growth": -0.2, "operating_cash_flow_growth": -0.4, "total_debt_growth": 0.3}
    assert ratio_risk_score(safe) == 0
    assert temporal_risk_score(adverse) > ratio_risk_score(adverse)


def test_logistic_baseline_and_trajectories():
    rows = [
        {"ticker": "A", "fiscal_year": 2021, "metrics": {"current_ratio": 2.0, "debt_to_assets": 0.2}},
        {"ticker": "B", "fiscal_year": 2021, "metrics": {"current_ratio": 0.5, "debt_to_assets": 0.9}},
    ]
    model = LogisticBaseline(iterations=50).fit(rows, [0, 1])
    scores = model.predict_scores(rows)
    assert scores[1] > scores[0]
    trajectory_rows = [rows[0], {"ticker": "A", "fiscal_year": 2022, "metrics": {"current_ratio": 0.8, "debt_to_assets": 0.7}}]
    assert len(temporal_trajectories(trajectory_rows)) == 1


def test_numeric_benchmark_treats_nonfinite_metrics_as_missing():
    assert ratio_risk_score({"current_ratio": float("nan")}) is None
    rows = [
        {"metrics": {"current_ratio": float("nan")}},
        {"metrics": {"current_ratio": 0.5}},
    ]
    scores = LogisticBaseline(iterations=2).fit(rows, [0, 1]).predict_scores(rows)
    assert all(0 <= score <= 1 for score in scores)


def test_numeric_benchmark_rejects_invalid_training_contracts():
    with pytest.raises(ValueError, match="positive and finite"):
        LogisticBaseline(learning_rate=float("nan"))
    with pytest.raises(ValueError, match="both classes"):
        LogisticBaseline(iterations=2).fit([{"metrics": {}}, {"metrics": {}}], [False, True])
