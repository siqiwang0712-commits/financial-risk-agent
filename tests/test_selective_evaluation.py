from research.selective_evaluation import evaluate_decisions, risk_coverage_curve


def test_explicit_selective_rates() -> None:
    result = evaluate_decisions([0, 1, 1, 0], ["PASS", "FLAG", "REVIEW", "ABSTAIN"])
    assert result["coverage"] == 0.5
    assert result["selective_error"] == 0.0
    assert result["review_rate"] == 0.25
    assert result["abstention_rate"] == 0.25
    assert result["unsupported_authorized_decision_rate"] == "NOT_ESTIMABLE"


def test_authorization_error_denominators_are_distinct() -> None:
    result = evaluate_decisions([0, 1, 1, 0], ["FLAG", "FLAG", "REVIEW", "REVIEW"])
    assert result["selective_error"] == 0.5
    assert result["erroneous_authorized_decision_rate"] == 0.25


def test_support_and_reference_rates() -> None:
    result = evaluate_decisions(
        [0, 1], ["PASS", "FLAG"], support_verified=[True, False], in_reference=[False, True]
    )
    assert result["unsupported_authorized_decision_rate"] == 0.5
    assert result["out_of_reference_authorization_rate"] == 0.5


def test_risk_coverage_curve_is_deterministic() -> None:
    first = risk_coverage_curve([0, 1, 1], [0.1, 0.9, 0.6])
    second = risk_coverage_curve([0, 1, 1], [0.1, 0.9, 0.6])
    assert first == second
    assert first[-1]["coverage"] == 1.0
