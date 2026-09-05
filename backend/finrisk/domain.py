from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Evidence:
    document: str
    page: int
    source_text: str
    fiscal_year: int | None = None
    confidence: float = 1.0
    verified: bool = False


@dataclass(frozen=True)
class FinancialValue:
    line_item: str
    value: float | None
    fiscal_year: int
    statement: str
    unit: str = "currency"
    currency: str = "USD"
    document: str = ""
    page: int = 0
    source_text: str = ""
    confidence: float = 1.0
    restated: bool = False


@dataclass
class Metric:
    name: str
    value: float | None
    formula: str
    inputs: dict[str, float | None]
    fiscal_year: int
    missing_reason: str | None = None


@dataclass
class ModelResult:
    name: str
    output: float | int | None
    interpretation: str
    applicability: str
    inputs: dict[str, float | None]
    formula: str
    missing_components: list[str] = field(default_factory=list)


@dataclass
class RuleSignal:
    rule_id: str
    category: str
    severity: str
    score_delta: float
    rationale: str
    evidence: list[str]


@dataclass
class NarrativeClaim:
    claim: str
    risk_category: str
    evidence: Evidence
    polarity: str = "neutral"


@dataclass
class Contradiction:
    category: str
    management_claim: str
    conflicting_evidence: list[str]
    interpretation: str
    evidence: Evidence


@dataclass
class Assessment:
    company: str
    reporting_period: str
    overall_score: float
    risk_level: str
    confidence: float
    dimensions: dict[str, dict[str, Any]]
    metrics: dict[str, Metric]
    models: list[ModelResult]
    triggered_rules: list[RuleSignal]
    contradictions: list[Contradiction]
    missing_information: list[str]
    disclaimer: str = "Risk scores are heuristic assessment scores, not bankruptcy probabilities or investment advice."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

