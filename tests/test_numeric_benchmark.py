from finrisk.numeric_benchmark import (
    LogisticBaseline,
    ratio_risk_score,
    temporal_risk_score,
    temporal_trajectories,
)


def test_numeric_scores_are_missing_aware_and_temporal():
    assert ratio_risk_score({}) == 0.5
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
