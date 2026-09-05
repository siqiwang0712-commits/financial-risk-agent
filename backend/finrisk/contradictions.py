from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .domain import Contradiction, NarrativeClaim


@dataclass(frozen=True)
class NumericCheck:
    metric: str
    label: str
    predicate: Callable[[float], bool]


CHECKS: dict[str, tuple[NumericCheck, ...]] = {
    "liquidity": (
        NumericCheck("cash_growth", "Cash declined by more than 10%", lambda x: x < -0.10),
        NumericCheck("operating_cash_flow_growth", "Operating cash flow declined by more than 10%", lambda x: x < -0.10),
        NumericCheck("short_term_debt_growth", "Short-term debt increased by more than 20%", lambda x: x > 0.20),
        NumericCheck("current_ratio", "Current ratio is below 1.0", lambda x: x < 1.0),
    ),
    "solvency_leverage": (
        NumericCheck("debt_to_assets", "Debt-to-assets exceeds 60%", lambda x: x > 0.60),
        NumericCheck("liabilities_to_assets", "Liabilities-to-assets exceeds 80%", lambda x: x > 0.80),
        NumericCheck("interest_coverage", "Interest coverage is below 1.5x", lambda x: x < 1.5),
        NumericCheck("total_debt_growth", "Total debt increased by more than 20%", lambda x: x > 0.20),
    ),
    "profitability": (
        NumericCheck("revenue_growth", "Revenue declined by more than 5%", lambda x: x < -0.05),
        NumericCheck("net_income_growth", "Net income declined by more than 15%", lambda x: x < -0.15),
        NumericCheck("operating_margin_change", "Operating margin deteriorated by more than 2 percentage points", lambda x: x < -0.02),
        NumericCheck("net_margin", "Net margin is negative", lambda x: x < 0),
    ),
    "cash_flow": (
        NumericCheck("operating_cash_flow_growth", "Operating cash flow declined by more than 15%", lambda x: x < -0.15),
        NumericCheck("free_cash_flow", "Free cash flow is negative", lambda x: x < 0),
        NumericCheck("fcf_growth", "Free cash flow declined by more than 20%", lambda x: x < -0.20),
        NumericCheck("cfo_to_net_income", "Cash conversion is below 0.8x", lambda x: x < 0.8),
    ),
    "earnings_quality": (
        NumericCheck("cfo_to_net_income", "Operating cash flow is below 80% of net income", lambda x: x < 0.8),
        NumericCheck("accounts_receivable_growth_gap", "Receivables growth exceeds revenue growth by 15 percentage points", lambda x: x > 0.15),
        NumericCheck("inventory_growth_gap", "Inventory growth exceeds revenue growth by 15 percentage points", lambda x: x > 0.15),
        NumericCheck("free_cash_flow", "Free cash flow is negative", lambda x: x < 0),
    ),
    "business_going_concern": (
        NumericCheck("working_capital", "Working capital is negative", lambda x: x < 0),
        NumericCheck("operating_cash_flow", "Operating cash flow is negative", lambda x: x < 0),
        NumericCheck("net_income", "Net income is negative", lambda x: x < 0),
        NumericCheck("going_concern_doubt", "Auditor/management disclosed substantial doubt", lambda x: bool(x)),
    ),
}


def consistency_facts(metrics: dict[str, float | None], raw: dict[str, float | None]) -> dict[str, float | None]:
    facts = dict(raw) | dict(metrics)
    revenue_growth = facts.get("revenue_growth")
    receivables_growth = facts.get("accounts_receivable_growth")
    inventory_growth = facts.get("inventory_growth")
    facts["accounts_receivable_growth_gap"] = None if revenue_growth is None or receivables_growth is None else receivables_growth - revenue_growth
    facts["inventory_growth_gap"] = None if revenue_growth is None or inventory_growth is None else inventory_growth - revenue_growth
    return facts


def detect_contradictions(claims: list[NarrativeClaim], facts: dict[str, float | None]) -> list[Contradiction]:
    """Compare optimistic narrative claims with category-specific numeric tests.

    Two independent numeric conflicts are required to reduce single-ratio false
    positives. This is an inconsistency signal and never an allegation of fraud.
    """
    out = []
    enriched = consistency_facts(facts, facts)
    for claim in claims:
        if claim.polarity != "positive" or claim.risk_category not in CHECKS:
            continue
        conflicts = []
        for check in CHECKS[claim.risk_category]:
            value = enriched.get(check.metric)
            if value is not None and check.predicate(value):
                conflicts.append(f"{check.label} [{check.metric}={value:.4g}]")
        minimum = 1 if claim.risk_category == "business_going_concern" and enriched.get("going_concern_doubt") else 2
        if len(conflicts) >= minimum:
            out.append(Contradiction(
                claim.risk_category, claim.claim, conflicts,
                "The narrative is more optimistic than the available indicators. This is a traceable consistency signal, not evidence of fraud or misstatement.",
                claim.evidence,
            ))
    return out
