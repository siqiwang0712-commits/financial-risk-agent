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
    verification_status: str = "unverified"
    source: str | None = None
    company: str | None = None
    period: str | None = None
    quote: str | None = None
    value: float | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.source is None:
            object.__setattr__(self, "source", self.document)
        if self.quote is None:
            object.__setattr__(self, "quote", self.source_text)
        if self.period is None and self.fiscal_year is not None:
            object.__setattr__(self, "period", str(self.fiscal_year))


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
    source_type: str = "document"
    taxonomy: str | None = None
    concept: str | None = None
    accession: str | None = None
    filed_at: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    original_unit: str | None = None
    provenance_url: str | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    line_item: str
    fiscal_year: int
    status: str
    authoritative_source: str
    xbrl_value: float | None
    document_value: float | None
    absolute_difference: float | None
    relative_difference: float | None
    explanation: str
    xbrl_provenance: FinancialValue | None = None
    document_provenance: FinancialValue | None = None


@dataclass
class Metric:
    name: str
    value: float | None
    formula: str
    inputs: dict[str, float | None]
    fiscal_year: int
    missing_reason: str | None = None
    source_refs: list[Evidence] = field(default_factory=list)


@dataclass
class ModelResult:
    name: str
    output: float | int | None
    interpretation: str
    applicability: str
    inputs: dict[str, float | None]
    formula: str
    missing_components: list[str] = field(default_factory=list)
    derived_outputs: dict[str, float] = field(default_factory=dict)


@dataclass
class RuleSignal:
    rule_id: str
    category: str
    severity: str
    score_delta: float
    rationale: str
    evidence: list[str]
    source_refs: list[Evidence] = field(default_factory=list)
    family: str | None = None
    required_inputs: list[str] = field(default_factory=list)
    input_provenance: dict[str, list[Evidence]] = field(default_factory=dict)


@dataclass
class NarrativeClaim:
    claim: str
    risk_category: str
    evidence: Evidence
    polarity: str = "neutral"
    claim_target: str = "category_general"
    direction: str = "neutral"
    time_horizon: str = "unspecified"
    basis: str = "management_statement"
    qualifiers: tuple[str, ...] = ()
    required_evidence_types: tuple[str, ...] = ()


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
    overall_score: float | None
    risk_level: str
    confidence: float
    dimensions: dict[str, dict[str, Any]]
    metrics: dict[str, Metric]
    models: list[ModelResult]
    triggered_rules: list[RuleSignal]
    contradictions: list[Contradiction]
    missing_information: list[str]
    confidence_components: dict[str, float] = field(default_factory=dict)
    evidence_graph: dict[str, Any] = field(default_factory=dict)
    # `evidence_quality` is *the same index* as `confidence`: the weighted
    # composite of `confidence_components`. They are two names for one number and
    # are always equal - a consumer must not read the pair as two independent
    # measurements. `confidence_semantics` travels with them so the distinction
    # that *is* real (`evidence_coverage` != `evidence_quality`) cannot be
    # mistaken for this one, and so neither number is read as a probability.
    evidence_quality: float = 0.0
    evidence_coverage: float = 0.0
    confidence_semantics: str = "EVIDENCE_QUALITY_INDEX_NOT_A_PROBABILITY"
    reliability_status: str = "UNCALIBRATED"
    # Computed once, on the same fact set that produced `contradictions`, so the
    # claim-level classification and the contradiction list cannot disagree.
    claim_consistency_evaluations: list[dict[str, Any]] = field(default_factory=list)
    disclosure_tensions: list[dict[str, Any]] = field(default_factory=list)
    # Nullable rates distinguish "no extracted claims" from "claims were
    # extracted but none verified".  Conflating those states turns an empty
    # denominator into a false 100% unsupported-claim result.
    claim_verification_summary: dict[str, Any] = field(default_factory=dict)
    # Declared vs reachable rule coverage. The rule set is quoted publicly as "68
    # versioned expert rules"; 25 of those reference facts no extractor here
    # produces, so they can only fire when a caller supplies the facts directly.
    # Published with every assessment so the two numbers travel together.
    rule_coverage: dict[str, Any] = field(default_factory=dict)
    disclaimer: str = "Risk scores are heuristic assessment scores, not bankruptcy probabilities or investment advice."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
