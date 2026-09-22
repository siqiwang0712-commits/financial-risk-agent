from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .domain import Contradiction, NarrativeClaim

_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "consistency_policy.json"


def _normalized_text_hash(path: Path) -> str:
    """Hash text with Python's universal-newline normalization."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


CONSISTENCY_POLICY = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
CONSISTENCY_POLICY_HASH = _normalized_text_hash(_POLICY_PATH)


def _configured(metric: str) -> Callable[[float], bool]:
    rule = CONSISTENCY_POLICY["thresholds"][metric]
    operator = rule["operator"]
    threshold = rule.get("value")
    if operator == "<":
        return lambda value: value < threshold
    if operator == ">":
        return lambda value: value > threshold
    return lambda value: bool(value)


@dataclass(frozen=True)
class NumericCheck:
    metric: str
    label: str
    predicate: Callable[[float], bool]


@dataclass(frozen=True)
class ClaimConsistencyEvaluation:
    claim: str
    risk_dimension: str
    claim_target: str
    required_evidence_types: tuple[str, ...]
    available_evidence_types: tuple[str, ...]
    missing_evidence_types: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    opposing_evidence: tuple[str, ...]
    classification: str
    reason_code: str
    policy_version: str = CONSISTENCY_POLICY["version"]
    policy_hash: str = CONSISTENCY_POLICY_HASH

    def to_dict(self) -> dict:
        return asdict(self)


CHECKS: dict[str, tuple[NumericCheck, ...]] = {
    "liquidity": (
        NumericCheck("cash_growth", "Cash declined by more than 10%", _configured("cash_growth")),
        NumericCheck("operating_cash_flow_growth", "Operating cash flow declined by more than 10%", _configured("operating_cash_flow_growth")),
        NumericCheck("short_term_debt_growth", "Short-term debt increased by more than 20%", _configured("short_term_debt_growth")),
        NumericCheck("current_ratio", "Current ratio is below 1.0", _configured("current_ratio")),
    ),
    "solvency_leverage": (
        NumericCheck("debt_to_assets", "Debt-to-assets exceeds 60%", _configured("debt_to_assets")),
        NumericCheck("liabilities_to_assets", "Liabilities-to-assets exceeds 80%", _configured("liabilities_to_assets")),
        NumericCheck("interest_coverage", "Interest coverage is below 1.5x", _configured("interest_coverage")),
        NumericCheck("total_debt_growth", "Total debt increased by more than 20%", _configured("total_debt_growth")),
    ),
    "profitability": (
        NumericCheck("revenue_growth", "Revenue declined by more than 5%", _configured("revenue_growth")),
        NumericCheck("net_income_growth", "Net income declined by more than 15%", _configured("net_income_growth")),
        NumericCheck("operating_margin_change", "Operating margin deteriorated by more than 2 percentage points", _configured("operating_margin_change")),
        NumericCheck("net_margin", "Net margin is negative", _configured("net_margin")),
    ),
    "cash_flow": (
        NumericCheck(
            "operating_cash_flow_growth",
            "Operating cash flow declined",
            _configured("cash_flow_operating_cash_flow_growth"),
        ),
        NumericCheck("free_cash_flow", "Free cash flow is negative", _configured("free_cash_flow")),
        NumericCheck("fcf_growth", "Free cash flow declined by more than 20%", _configured("fcf_growth")),
        NumericCheck("cfo_to_net_income", "Cash conversion is below 0.8x", _configured("cfo_to_net_income")),
    ),
    "earnings_quality": (
        NumericCheck("cfo_to_net_income", "Operating cash flow is below 80% of net income", _configured("cfo_to_net_income")),
        NumericCheck("accounts_receivable_growth_gap", "Receivables growth exceeds revenue growth by 15 percentage points", _configured("accounts_receivable_growth_gap")),
        NumericCheck("inventory_growth_gap", "Inventory growth exceeds revenue growth by 15 percentage points", _configured("inventory_growth_gap")),
        NumericCheck("free_cash_flow", "Free cash flow is negative", _configured("free_cash_flow")),
    ),
    "business_going_concern": (
        NumericCheck("working_capital", "Working capital is negative", _configured("working_capital")),
        NumericCheck("operating_cash_flow", "Operating cash flow is negative", _configured("operating_cash_flow")),
        NumericCheck("net_income", "Net income is negative", _configured("net_income")),
        NumericCheck("going_concern_doubt", "Auditor/management disclosed substantial doubt", _configured("going_concern_doubt")),
    ),
}


EVIDENCE_CONSTRUCTS: dict[str, dict[str, tuple[str, ...]]] = {
    "liquidity": {
        "liquidity_position": ("current_ratio", "working_capital"),
        "cash_generation": ("cash_growth", "operating_cash_flow_growth"),
        "funding_pressure": ("short_term_debt_growth", "total_debt_growth"),
        "liquid_investments": ("marketable_securities", "short_term_investments"),
        "funding_access": ("committed_credit_capacity", "debt_market_access"),
    },
    "solvency_leverage": {
        "capital_structure": ("debt_to_assets", "liabilities_to_assets"),
        "debt_service": ("interest_coverage",),
        "debt_trajectory": ("total_debt_growth",),
    },
    "profitability": {
        "profit_level": ("net_margin", "operating_margin"),
        "profit_trajectory": ("net_income_growth", "operating_margin_change"),
        "demand_trajectory": ("revenue_growth",),
    },
    "cash_flow": {
        "cash_generation": ("operating_cash_flow", "operating_cash_flow_growth"),
        "free_cash_flow": ("free_cash_flow", "fcf_growth"),
        "cash_conversion": ("cfo_to_net_income",),
    },
    "earnings_quality": {
        "cash_conversion": ("cfo_to_net_income", "free_cash_flow"),
        "working_capital_quality": (
            "accounts_receivable_growth_gap",
            "inventory_growth_gap",
        ),
    },
    "business_going_concern": {
        "operating_viability": ("net_income", "operating_cash_flow"),
        "near_term_liquidity": ("working_capital",),
        "explicit_disclosure": ("going_concern_doubt",),
    },
}

DEFAULT_REQUIRED_CONSTRUCTS = {
    "liquidity": ("liquidity_position", "cash_generation", "funding_pressure"),
}


def evaluate_claim_consistency(
    claim: NarrativeClaim, facts: dict[str, float | None]
) -> ClaimConsistencyEvaluation:
    enriched = consistency_facts(facts, facts)
    constructs = EVIDENCE_CONSTRUCTS.get(claim.risk_category, {})
    required = claim.required_evidence_types or DEFAULT_REQUIRED_CONSTRUCTS.get(
        claim.risk_category, tuple(constructs)
    )
    available = tuple(
        construct
        for construct in required
        if any(enriched.get(metric) is not None for metric in constructs.get(construct, ()))
    )
    missing = tuple(item for item in required if item not in available)
    opposing = tuple(
        f"{check.label} [{check.metric}={enriched[check.metric]:.4g}]"
        for check in CHECKS.get(claim.risk_category, ())
        if enriched.get(check.metric) is not None
        and check.predicate(enriched[check.metric])
    )
    supporting = tuple(
        f"No adverse threshold breach for {check.metric} [{check.metric}={enriched[check.metric]:.4g}]"
        for check in CHECKS.get(claim.risk_category, ())
        if enriched.get(check.metric) is not None
        and not check.predicate(enriched[check.metric])
    )
    verified = claim.evidence.verification_status == "verified"
    if not verified:
        classification, reason = "INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVIDENCE"
    elif missing:
        classification, reason = "INCOMPLETE_CONTEXT", "CLAIM_CONTEXT_INCOMPLETE"
    elif claim.polarity != "positive" and claim.direction != "positive":
        classification, reason = "NOT_APPLICABLE", "CLAIM_NOT_OPTIMISTIC"
    elif len(opposing) >= int(CONSISTENCY_POLICY["material_opposition_count"]):
        classification, reason = "MATERIAL_CONTRADICTION", "SEVERE_VERIFIED_SIGNAL"
    elif opposing:
        classification, reason = "TENSION", "PARTIAL_NUMERIC_TENSION"
    else:
        classification, reason = "NO_CONTRADICTION", "NO_ADVERSE_CONFLICT"
    return ClaimConsistencyEvaluation(
        claim.claim,
        claim.risk_category,
        claim.claim_target,
        tuple(required),
        available,
        missing,
        supporting,
        opposing,
        classification,
        reason,
    )


def consistency_facts(metrics: dict[str, float | None], raw: dict[str, float | None]) -> dict[str, float | None]:
    facts = dict(raw) | dict(metrics)
    revenue_growth = facts.get("revenue_growth")
    receivables_growth = facts.get("accounts_receivable_growth")
    inventory_growth = facts.get("inventory_growth")
    if facts.get("accounts_receivable_growth_gap") is None:
        facts["accounts_receivable_growth_gap"] = None if revenue_growth is None or receivables_growth is None else receivables_growth - revenue_growth
    if facts.get("inventory_growth_gap") is None:
        facts["inventory_growth_gap"] = None if revenue_growth is None or inventory_growth is None else inventory_growth - revenue_growth
    return facts


def detect_contradictions(claims: list[NarrativeClaim], facts: dict[str, float | None]) -> list[Contradiction]:
    """Compare optimistic narrative claims with category-specific numeric tests.

    Two independent numeric conflicts are required to reduce single-ratio false
    positives. This is an inconsistency signal and never an allegation of fraud.
    """
    out = []
    for claim in claims:
        evaluation = evaluate_claim_consistency(claim, facts)
        if evaluation.classification == "MATERIAL_CONTRADICTION":
            out.append(Contradiction(
                claim.risk_category, claim.claim, list(evaluation.opposing_evidence),
                "The narrative is more optimistic than the available indicators. This is a traceable consistency signal, not evidence of fraud or misstatement.",
                claim.evidence,
            ))
    return out
