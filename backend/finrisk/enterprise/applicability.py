from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from ..domain import ModelResult


class ApplicabilityStatus(StrEnum):
    APPLICABLE = "APPLICABLE"
    LIMITED = "LIMITED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ApplicabilityDecision:
    model: str
    status: ApplicabilityStatus
    reasons: tuple[str, ...]
    missing_components: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


MODEL_REQUIREMENTS = {
    "altman": {"working_capital", "total_assets", "retained_earnings", "ebit", "market_value_equity", "total_liabilities", "revenue"},
    "beneish": {"accounts_receivable", "revenue", "gross_profit", "total_assets", "depreciation", "ppe", "sga"},
    "piotroski": {"net_income", "operating_cash_flow", "total_assets", "current_assets", "current_liabilities", "shares_outstanding"},
    "ohlson": {"total_assets", "total_liabilities", "working_capital", "current_liabilities", "current_assets", "net_income", "funds_from_operations"},
}
FINANCIAL_INDUSTRIES = {"bank", "banking", "insurance", "financial_institution", "broker_dealer"}


def route_model(model: str, industry: str, facts: dict[str, object]) -> ApplicabilityDecision:
    key = model.lower().replace("_score", "").replace("-", "_")
    if key not in MODEL_REQUIREMENTS:
        raise KeyError(f"unknown model: {model}")
    missing = tuple(sorted(name for name in MODEL_REQUIREMENTS[key] if facts.get(name) is None))
    reasons = []
    normalized_industry = industry.lower().strip()
    if normalized_industry in FINANCIAL_INDUSTRIES:
        return ApplicabilityDecision(key, ApplicabilityStatus.NOT_APPLICABLE, ("regulated financial institutions have structurally different balance sheets",), missing)
    if key == "altman" and normalized_industry not in {"manufacturing", "industrial", "public_manufacturer"}:
        reasons.append("original public-manufacturer population does not match the supplied industry")
    if missing:
        reasons.append(f"missing {len(missing)} required component(s)")
    status = ApplicabilityStatus.APPLICABLE if not reasons else ApplicabilityStatus.LIMITED
    if len(missing) == len(MODEL_REQUIREMENTS[key]):
        status = ApplicabilityStatus.NOT_APPLICABLE
    return ApplicabilityDecision(key, status, tuple(reasons or ("assumptions and required inputs satisfied",)), missing)


def applicability_report(industry: str, facts: dict[str, object]) -> list[dict]:
    return [route_model(model, industry, facts).to_dict() for model in MODEL_REQUIREMENTS]


def enforce_applicability(
    results: list[ModelResult], industry: str, facts: dict[str, object]
) -> list[ModelResult]:
    model_keys = {
        "Altman Z-Score": "altman",
        "Beneish M-Score": "beneish",
        "Piotroski F-Score": "piotroski",
        "Ohlson O-Score": "ohlson",
    }
    for result in results:
        decision = route_model(model_keys[result.name], industry, facts)
        missing = sorted(
            set(result.missing_components) | set(decision.missing_components)
        )
        status = decision.status
        reasons = [reason for reason in decision.reasons if not reason.startswith("missing ")]
        if missing and status is ApplicabilityStatus.APPLICABLE:
            status = ApplicabilityStatus.LIMITED
        if missing:
            reasons.append(f"missing {len(missing)} required component(s)")
        result.applicability = f"{status}: {'; '.join(reasons)}"
        result.missing_components = missing
        if decision.status is ApplicabilityStatus.NOT_APPLICABLE:
            result.output = None
            result.derived_outputs = {}
    return results
