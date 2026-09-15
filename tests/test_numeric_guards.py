"""Numeric and decision guards for the batch-1 correctness fixes.

Each test is a *guard*: it fails on the pre-fix code, so a future refactor that
reintroduces the defect is caught here rather than in a published number.
"""
import math
from pathlib import Path

from finrisk.facts import build_facts
from finrisk.metrics import _safe_div, calculate_metrics
from finrisk.models import beneish_m, ohlson_o
from finrisk.normalization import parse_number
from finrisk.parser import DocumentParser
from finrisk.pipeline import FinRiskPipeline
from finrisk.rules import RuleEngine

ROOT = Path(__file__).resolve().parents[1]


# --- FIN-05: `dict.get(k, default)` must not shadow a present-but-None value ---
def test_ebit_falls_back_to_operating_income_when_ebit_is_present_but_none():
    metrics = calculate_metrics(
        {"ebit": None, "operating_income": 68, "interest_expense": 10}, 2025
    )
    assert metrics["interest_coverage"].value == 6.8


def test_interest_coverage_is_independent_of_expense_sign_convention():
    positive = calculate_metrics({"ebit": 60, "interest_expense": 10}, 2025)
    negative = calculate_metrics({"ebit": 60, "interest_expense": -10}, 2025)
    assert positive["interest_coverage"].value == 6
    assert negative["interest_coverage"].value == 6
    assert negative["interest_coverage"].formula == "EBIT / abs(interest_expense)"


# --- FIN-07: a non-finite quotient must not leak as `inf` ---------------------
def test_safe_div_rejects_non_finite_results():
    assert _safe_div(1e9, 1e-300) is None
    assert _safe_div(1e9, 0) is None
    assert _safe_div(None, 5) is None
    assert _safe_div(10.0, 2.0) == 5.0


# --- FIN-09: unit handling ----------------------------------------------------
def test_percent_is_a_ratio_not_a_scaled_amount():
    assert parse_number("12.5%") == 0.125
    assert parse_number("12.5%", "millions") == 0.125


def test_comma_is_disambiguated_between_thousands_and_decimal():
    assert parse_number("1,234") == 1234
    assert parse_number("1,234,567") == 1_234_567
    assert parse_number("1234,56") == 1234.56
    assert parse_number("0,5") == 0.5
    # A negative in parentheses keeps its sign through both paths.
    assert parse_number("(1,250)", "millions") == -1_250_000_000


def test_scale_header_variants_are_detected():
    parser = DocumentParser()
    thousands = parser.extract_values(
        {1: "CONSOLIDATED BALANCE SHEET\n(000s)\nCash and cash equivalents 1,250"}, "s", 2025
    )
    assert thousands[0].value == 1_250_000
    dollars = parser.extract_values(
        {1: "CONSOLIDATED BALANCE SHEET\nCash and cash equivalents 1,250"}, "s", 2025
    )
    assert dollars[0].value == 1250


# --- FIN-08: Beneish must reject a NaN index, not read it as "no signal" ------
def test_beneish_rejects_non_finite_denominators():
    base = {
        "accounts_receivable": 100, "revenue": 1000, "gross_profit": 400,
        "current_assets": 500, "current_liabilities": 200, "ppe": 100,
        "total_assets": 1000, "depreciation": 10, "sga": 50, "long_term_debt": 100,
        "net_income": 50, "operating_cash_flow": 60,
    }
    result = beneish_m({**base, "revenue": float("nan")}, base)
    assert result.output is None
    assert "No elevated" not in result.interpretation


# --- FIN-14: Ohlson must not raise OverflowError on extreme inputs ------------
def test_ohlson_probability_saturates_without_overflow():
    on = {
        "total_assets": 1000, "total_liabilities": 1, "working_capital": 100,
        "current_liabilities": 10, "current_assets": 200, "net_income": -5,
        "funds_from_operations": 1e6, "prior_net_income": -4, "gnp_price_index": 1,
    }
    result = ohlson_o(on)
    assert result.derived_outputs["probability"] == 0.0
    assert math.isfinite(result.output)


# --- FIN-15: growth across a sign change is undefined -------------------------
def test_growth_is_undefined_across_a_sign_change():
    metrics = calculate_metrics(
        {"revenue": 50, "net_income": -50}, 2025, {"revenue": 100, "net_income": -100}
    )
    assert metrics["net_income_growth"].value is None
    # A genuine decline from a positive base is still reported.
    decline = calculate_metrics({"revenue": 80}, 2025, {"revenue": 100})
    assert decline["revenue_growth"].value is not None


# --- FIN-18: cash conversion is undefined when earnings are not positive ------
def test_cfo_to_net_income_is_withheld_for_non_positive_earnings():
    assert calculate_metrics(
        {"operating_cash_flow": 120, "net_income": -100}, 2025
    )["cfo_to_net_income"].value is None
    assert calculate_metrics(
        {"operating_cash_flow": 120, "net_income": 100}, 2025
    )["cfo_to_net_income"].value == 1.2


# --- FIN-12: negative-EBITDA leverage must not be silently exempt -------------
def test_negative_ebitda_leverage_fires_the_rule():
    facts = build_facts({"total_debt": 100, "ebitda": -20}, None, 2025, {}, [])
    assert facts["negative_ebitda_leverage"] is True
    fired = {s.rule_id for s in RuleEngine.from_file(ROOT / "rules" / "rules.json").evaluate(facts)}
    assert "SOL_009" in fired
    # No debt, or positive EBITDA, must not fire.
    quiet = build_facts({"total_debt": 0, "ebitda": -20}, None, 2025, {}, [])
    assert quiet["negative_ebitda_leverage"] is False


# --- FIN-03: `*_change` must compare like with like ---------------------------
def test_change_metrics_are_zero_for_proportionally_scaled_periods():
    period = {
        "revenue": 1000, "net_income": 100, "operating_cash_flow": 100, "capital_expenditure": 0,
        "total_debt": 100, "cash": 100, "accounts_receivable": 100, "inventory": 100, "gross_profit": 400,
        "total_assets": 1000, "shareholder_equity": 500, "current_assets": 400, "current_liabilities": 200,
        "accounts_payable": 100, "operating_income": 200,
    }
    current = dict(period)
    previous = {key: value / 2 for key, value in period.items()}
    metrics = calculate_metrics(current, 2025, previous)
    facts = build_facts(current, previous, 2025, metrics, [])
    changes = {key: facts[key] for key in facts if key.endswith("_change")}
    assert changes, "expected change metrics to be produced"
    assert all(value in (0, None) for value in changes.values()), changes


# --- FIN-02: one risk signal must not be scored twice -------------------------
def test_beneish_is_not_double_counted_between_registry_and_model_mapping():
    engine = RuleEngine.from_file(ROOT / "rules" / "rules.json")
    assert not engine.evaluate({"beneish_m_score": 0.5})
    pipeline = FinRiskPipeline(ROOT)
    mappings = [m for m in pipeline.model_scoring["mappings"] if m["metric"] == "beneish_m_score"]
    assert len(mappings) == 1


def test_duplicate_signal_guard_rejects_a_reintroduced_duplicate():
    pipeline = FinRiskPipeline(ROOT)
    duplicate = {
        "id": "DUP_001", "category": "accounting", "severity": "high",
        "conditions": [{"metric": "beneish_m_score", "operator": ">", "value": -1.78}],
        "effect": {"score_delta": 18}, "rationale": "duplicate",
    }
    pipeline.rules.rules.append(duplicate)
    try:
        try:
            pipeline._assert_signals_are_not_double_counted()
        except ValueError:
            pass
        else:
            raise AssertionError("guard did not reject a duplicate signal")
    finally:
        pipeline.rules.rules.pop()


def test_metric_calculation_never_emits_nonfinite_values_from_direct_inputs():
    metrics = calculate_metrics(
        {
            "revenue": float("nan"),
            "operating_cash_flow": float("inf"),
            "capital_expenditure": 10,
            "total_debt": True,
        },
        2025,
    )
    assert metrics["fcf_margin"].value is None
    assert metrics["free_cash_flow"].value is None
    assert metrics["debt_to_assets"].value is None


def test_financial_models_reject_boolean_inputs_as_invalid():
    result = ohlson_o(
        {
            "total_assets": True,
            "total_liabilities": 10,
            "working_capital": 5,
            "current_liabilities": 5,
            "current_assets": 10,
            "net_income": 1,
            "funds_from_operations": 1,
            "prior_net_income": 1,
            "gnp_price_index": 1,
        }
    )
    assert result.output is None
    assert result.interpretation == "Invalid input domain"
