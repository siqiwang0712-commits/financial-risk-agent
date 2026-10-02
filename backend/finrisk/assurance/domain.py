from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class AssuranceStatus(StrEnum):
    PASSED = "PASSED"
    RESTRICTED = "RESTRICTED"
    FAILED = "FAILED"


class EvidenceAssuranceState(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class EvidenceFragilityState(StrEnum):
    STABLE = "STABLE"
    SENSITIVE = "SENSITIVE"
    FRAGILE = "FRAGILE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class DistributionValidityState(StrEnum):
    IN_REFERENCE = "IN_REFERENCE"
    WARNING = "WARNING"
    OUTSIDE_REFERENCE = "OUTSIDE_REFERENCE"
    UNKNOWN = "UNKNOWN"


class PolicyMaturity(StrEnum):
    HEURISTIC_POLICY = "HEURISTIC_POLICY"
    CALIBRATED_INTERNAL = "CALIBRATED_INTERNAL"
    VALIDATED_EXTERNAL = "VALIDATED_EXTERNAL"


class SufficientEvidenceMethod(StrEnum):
    EXACT = "EXACT"
    GREEDY_APPROXIMATION = "GREEDY_APPROXIMATION"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True)
class FinancialFeatureVector:
    """Financial values only. Reporting availability is deliberately excluded."""

    values: dict[str, float | None]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportingObservabilityVector:
    """Whether expected fields were reported, never a financial-risk score input."""

    availability: dict[str, bool]

    @property
    def availability_rate(self) -> float | None:
        if not self.availability:
            return None
        return sum(self.availability.values()) / len(self.availability)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["availability_rate"] = self.availability_rate
        return payload


@dataclass(frozen=True)
class EvidenceDependency:
    dependency_id: str
    evidence_ids: tuple[str, ...]
    risk_dimension: str
    score: float | None
    claims: tuple[str, ...] = ()
    verified: bool = False


@dataclass(frozen=True)
class EvidenceAssurance:
    state: EvidenceAssuranceState
    material_path_count: int
    verified_path_count: int
    coverage: float
    verified_evidence_ids: tuple[str, ...] = ()
    supported_claims: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceFragility:
    state: EvidenceFragilityState
    largest_single_evidence_impact: float | None
    decision_flip_count: int
    decision_flip_rate: float | None
    severity_change_count: int
    affected_dimensions: tuple[str, ...] = ()
    affected_claims: tuple[str, ...] = ()
    ablations: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionSufficientEvidence:
    evidence_ids: tuple[str, ...]
    method: SufficientEvidenceMethod
    exact: bool
    preserves_proposed_decision: bool
    evaluated_subsets: int
    baseline_decision: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DistributionValidity:
    state: DistributionValidityState
    reference_name: str | None
    reference_version: str | None
    reference_scope: str | None
    evaluated_feature_count: int
    outside_feature_count: int
    reporting_availability_rate: float | None
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssuranceResult:
    proposed_decision: str
    final_decision: str
    automation_allowed: bool
    assurance_status: AssuranceStatus
    evidence_assurance: EvidenceAssurance
    evidence_fragility: EvidenceFragility
    distribution_validity: DistributionValidity
    decision_sufficient_evidence: DecisionSufficientEvidence
    policy_status: PolicyMaturity
    calibration_status: str
    reason_codes: tuple[str, ...]
    policy_version: str
    policy_hash: str
    certificate_hash: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
