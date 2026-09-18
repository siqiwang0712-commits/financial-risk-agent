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
    "beneish": {"accounts_receivable", "revenue", "gross_profit", "current_assets", "current_liabilities", "ppe", "total_assets", "depreciation", "sga", "long_term_debt", "net_income", "operating_cash_flow"},
    "piotroski": {"net_income", "operating_cash_flow", "total_assets", "long_term_debt", "current_assets", "current_liabilities", "shares_outstanding", "gross_profit", "revenue"},
    "ohlson": {"total_assets", "total_liabilities", "working_capital", "current_liabilities", "current_assets", "net_income", "funds_from_operations", "prior_net_income", "gnp_price_index"},
}
# Altman's other populations need a book-equity denominator instead of market
# value, and Z'' drops the asset-turnover term entirely. Kept out of
# MODEL_REQUIREMENTS so `applicability_report` still enumerates one entry per
# model family.
ALTMAN_VARIANT_REQUIREMENTS = {
    "public_manufacturer": MODEL_REQUIREMENTS["altman"],
    "private": {"working_capital", "total_assets", "retained_earnings", "ebit", "shareholder_equity", "total_liabilities", "revenue"},
    "non_manufacturer": {"working_capital", "total_assets", "retained_earnings", "ebit", "shareholder_equity", "total_liabilities"},
}
FINANCIAL_INDUSTRIES = {"bank", "banking", "insurance", "financial_institution", "broker_dealer"}


def route_model(model: str, industry: str, facts: dict[str, object], variant: str | None = None) -> ApplicabilityDecision:
    key = model.lower().replace("_score", "").replace("-", "_")
    if key not in MODEL_REQUIREMENTS:
        raise KeyError(f"unknown model: {model}")
    requirements = MODEL_REQUIREMENTS[key]
    if key == "altman" and variant in ALTMAN_VARIANT_REQUIREMENTS:
        requirements = ALTMAN_VARIANT_REQUIREMENTS[variant]
    missing = tuple(sorted(name for name in requirements if facts.get(name) is None))
    reasons = []
    normalized_industry = industry.lower().strip()
    if normalized_industry in FINANCIAL_INDUSTRIES:
        return ApplicabilityDecision(key, ApplicabilityStatus.NOT_APPLICABLE, ("regulated financial institutions have structurally different balance sheets",), missing)
    if key == "altman" and variant in (None, "public_manufacturer") and normalized_industry not in {"manufacturing", "industrial", "public_manufacturer"}:
        reasons.append("original public-manufacturer population does not match the supplied industry")
    if key == "altman" and variant == "non_manufacturer":
        reasons.append("non-manufacturer Z'' variant; original cut-offs do not apply")
    if key == "altman" and variant == "private":
        reasons.append("private-firm Z' variant; book equity replaces market value")
    if key == "piotroski":
        reasons.append("Piotroski-style proxy uses end-of-period asset denominators")
    if missing:
        reasons.append(f"missing {len(missing)} required component(s)")
    status = ApplicabilityStatus.APPLICABLE if not reasons else ApplicabilityStatus.LIMITED
    if len(missing) == len(requirements):
        status = ApplicabilityStatus.NOT_APPLICABLE
    return ApplicabilityDecision(key, status, tuple(reasons or ("assumptions and required inputs satisfied",)), missing)


def applicability_report(industry: str, facts: dict[str, object]) -> list[dict]:
    return [route_model(model, industry, facts).to_dict() for model in MODEL_REQUIREMENTS]


# Single source for the report label -> `MODEL_REQUIREMENTS` key mapping. The
# pipeline looks a configured model name up in this registry, so it must be the
# only copy: a second copy in another module is how a config rename turns into an
# unexplained 500 mid-request.
MODEL_KEYS: dict[str, str] = {
    "Altman Z-Score": "altman",
    "Beneish M-Score": "beneish",
    "Piotroski F-Score": "piotroski",
    "Ohlson O-Score": "ohlson",
}


def enforce_applicability(
    results: list[ModelResult], industry: str, facts: dict[str, object]
) -> list[ModelResult]:
    for result in results:
        key = MODEL_KEYS.get(result.name)
        if key is None:
            # Same failure mode the pipeline now rejects at construction time: an
            # unregistered model name must name itself instead of surfacing as a
            # bare KeyError in the middle of a request.
            raise ValueError(f"unregistered model name: {result.name!r}")
        decision = route_model(
            key, industry, facts,
            variant=result.derived_outputs.get("variant"),
        )
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
