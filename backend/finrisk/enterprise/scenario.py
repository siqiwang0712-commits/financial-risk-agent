from __future__ import annotations

from dataclasses import dataclass

from ..metrics import calculate_metrics


@dataclass(frozen=True)
class Scenario:
    name: str
    revenue_pct: float = 0.0
    margin_pp: float = 0.0
    interest_rate_bp: float = 0.0
    cfo_pct: float = 0.0
    receivable_days_pct: float = 0.0
    inventory_days_pct: float = 0.0
    refinancing_cost_pct: float = 0.0
    debt_pct: float = 0.0
    fx_pct: float = 0.0


def apply_scenario(values: dict[str, float], scenario: Scenario) -> dict[str, float]:
    stressed = dict(values)
    if "revenue" in stressed:
        stressed["revenue"] *= 1 + scenario.revenue_pct + scenario.fx_pct
    if "gross_profit" in stressed:
        stressed["gross_profit"] += values.get("revenue", 0) * scenario.margin_pp
    if "operating_income" in stressed:
        stressed["operating_income"] += values.get("revenue", 0) * scenario.margin_pp
    if "interest_expense" in stressed:
        debt = values.get("total_debt", 0)
        stressed["interest_expense"] += (
            debt * scenario.interest_rate_bp / 10_000
            + debt * scenario.refinancing_cost_pct
        )
    if "operating_cash_flow" in stressed:
        stressed["operating_cash_flow"] *= 1 + scenario.cfo_pct
    for key in ("short_term_debt", "long_term_debt", "total_debt"):
        if key in stressed:
            stressed[key] *= 1 + scenario.debt_pct
    if "accounts_receivable" in stressed:
        stressed["accounts_receivable"] *= 1 + scenario.receivable_days_pct
    if "inventory" in stressed:
        stressed["inventory"] *= 1 + scenario.inventory_days_pct
    return stressed


def compare_scenario(values: dict[str, float], year: int, scenario: Scenario) -> dict:
    stressed = apply_scenario(values, scenario)
    baseline_metrics = calculate_metrics(values, year)
    stressed_metrics = calculate_metrics(stressed, year)
    changes = {
        key: {
            "baseline": metric.value,
            "stressed": stressed_metrics[key].value,
            "formula": metric.formula,
        }
        for key, metric in baseline_metrics.items()
        if metric.value != stressed_metrics[key].value
    }
    return {
        "scenario": scenario.__dict__,
        "stressed_values": stressed,
        "metric_changes": changes,
        "calculation_mode": "deterministic",
    }
